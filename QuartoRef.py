#!/usr/bin/env python3
"""
QuartoRef - Quarto-optimized PubMed & DOI Metadata Fetcher & Sync Tool

Description:
    .qmd / .md ファイル内の [@pmid:ID] および [@doi:ID] タグを検出し、
    APIから書誌情報を取得して同名の CSL-JSON ファイルとして保存します。
    連続するタグを統合し、QuartoのYAMLフロントマターと連携します。
"""
from __future__ import annotations

__version__ = "1.2.1"

import argparse
import concurrent.futures
import io
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

# 外部ライブラリのチェック
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    from ruamel.yaml import YAML
    from dotenv import load_dotenv
except ImportError:
    print("Error: Required libraries are missing. Please run: pip install requests ruamel.yaml python-dotenv")
    sys.exit(1)

# .env ファイルの読み込み (システム環境変数を優先するため override=False)
load_dotenv(override=False)

# ==========================================
# ⚙️ ユーザー設定
# ==========================================
@dataclass(frozen=True)
class Settings:
    update_yaml: bool = True
    download_csl: bool = True
    pubmed_api_base: str = "https://pmc.ncbi.nlm.nih.gov/api/ctxp/v1/pubmed/"
    doi_api_base: str = "https://doi.org/"
    api_key: str | None = field(default_factory=lambda: os.getenv("NCBI_API_KEY"))
    email: str | None = field(default_factory=lambda: os.getenv("EMAIL"))
    api_timeout: float = 20.0
    csl_repo_url: str = "https://raw.githubusercontent.com/citation-style-language/styles/master/"

# ==========================================
# 🔍 正規表現パターン
# ==========================================
# 単一の引用タグ [@prefix:ID]
RE_TAG_PATTERN = r'@(pmid|doi):([^;\]\s]+)'
RE_TAG_EXTRACT = re.compile(RE_TAG_PATTERN)

# 連続する引用ブロックを検出 [@pmid:1] [@doi:10.123/abc]
RE_BLOCK = r'\[@(?:pmid|doi):[^\]]+\]'
RE_CONSECUTIVE = re.compile(f'({RE_BLOCK})(?:\\s*({RE_BLOCK}))+')

# ==========================================
# 📦 データモデル
# ==========================================

@dataclass
class ArticleMetadata:
    prefix: str  # 'pmid' or 'doi'
    raw_id: str   # e.g., '123' or '10.123/abc%3Bdef'
    csl_data: dict = field(default_factory=dict)
    error: str | None = None
    status_code: int = 200

    @classmethod
    def from_existing(cls, csl: dict[str, Any]) -> ArticleMetadata:
        """既存のJSONデータからArticleMetadataオブジェクトを復元"""
        full_id = csl.get("id", "")
        if ":" in full_id:
            prefix, raw_id = full_id.split(":", 1)
        else:
            prefix, raw_id = "unknown", full_id
        return cls(prefix=prefix, raw_id=raw_id, csl_data=csl)

    @property
    def full_id(self) -> str:
        """JSON内やMarkdown内で使用する一意のID (例: doi:10.123/abc%3Bdef)"""
        return f"{self.prefix}:{self.raw_id}"

    @property
    def is_valid(self) -> bool:
        return self.error is None and bool(self.csl_data)

    def to_csl_json(self) -> dict[str, Any]:
        """CSL-JSON形式のデータを正規化して返す"""
        csl = self.csl_data.copy() if self.csl_data else {}
        
        # 1. IDをタグと一致させる
        csl["id"] = self.full_id
        
        # 2. 文献タイプのマッピング (Crossref -> CSL-JSON)
        if "type" in csl:
            type_map = {
                "journal-article": "article-journal",
                "book-chapter": "chapter",
                "proceedings-article": "paper-conference",
                "monograph": "book",
                "reference-book": "book",
                "edited-book": "book",
                "reference-entry": "entry-encyclopedia",
                "report": "report",
                "dissertation": "thesis",
                "standard": "standard",
            }
            csl["type"] = type_map.get(csl["type"], csl["type"])
        else:
            csl["type"] = "article-journal"

        # 3. 配列フィールドの文字列化 (Pandoc/Quartoのパースエラー防止)
        string_fields = [
            "title", "container-title", "publisher", 
            "original-title", "short-title", "subtitle",
            "collection-title", "archive", "archive_location", 
            "event-title", "journal-title", "short-container-title",
            "ISSN", "ISBN", "PMID", "PMCID", "alternative-id", "subject"
        ]
        for f in string_fields:
            if f in csl:
                val = csl[f]
                if isinstance(val, list):
                    if len(val) > 0:
                        # 複数はカンマ区切りにする (ISSNなど)
                        csl[f] = ", ".join([str(x) for x in val])
                    else:
                        csl[f] = ""

        # 4. 不要なフィールドの削除 (大規模データやパースエラーの原因を除去)
        unwanted = ["reference", "content-domain", "abstract", "accepted", 
                    "published-print", "published-online", "link", "indexed", "created", "deposited",
                    "license", "assertion", "relation", "updated-by"]
        for f in unwanted:
            csl.pop(f, None)

        # 5. 必須フィールドの補完 (Quartoのビルドエラー防止)
        if not csl.get("title"):
            if self.error:
                csl["title"] = f"[Error] {self.error}"
            else:
                csl["title"] = f"[{self.full_id}] Title missing"
        
        if not csl.get("author"):
            csl["author"] = [{"family": f"{self.prefix.upper()} {self.raw_id}", "given": ""}]
            
        if not csl.get("issued"):
            csl["issued"] = {"date-parts": [[0]]}
            
        return csl

# ==========================================
# 🌐 API クライアント
# ==========================================

class BaseClient:
    def __init__(self, settings: Settings, rate: float, workers: int):
        self.settings = settings
        self.rate = rate
        self.workers = workers
        self.lock = threading.Lock()
        self.next_call = 0.0

        self.session = requests.Session()
        retry = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.mount("http://", HTTPAdapter(max_retries=retry))

    def _wait_rate_limit(self):
        with self.lock:
            now = time.time()
            wait_time = max(0.0, self.next_call - now)
            self.next_call = now + wait_time + (1.0 / self.rate)
        if wait_time > 0:
            time.sleep(wait_time)

class PubMedClient(BaseClient):
    def __init__(self, settings: Settings, override_key: str | None = None):
        api_key = override_key or settings.api_key
        if api_key:
            rate, workers = 9.0, 10
            self.api_key = api_key
        else:
            rate, workers = 3.0, 3
            self.api_key = None
        super().__init__(settings, rate, workers)

    def _fetch_single(self, raw_id: str) -> ArticleMetadata:
        self._wait_rate_limit()
        params = {"format": "csl", "id": raw_id}
        if self.api_key:
            params["api_key"] = self.api_key
        try:
            resp = self.session.get(self.settings.pubmed_api_base, params=params, timeout=self.settings.api_timeout)
            if resp.status_code == 404:
                return ArticleMetadata(prefix="pmid", raw_id=raw_id, error="Not found", status_code=404)
            resp.raise_for_status()
            return ArticleMetadata(prefix="pmid", raw_id=raw_id, csl_data=resp.json())
        except Exception as e:
            return ArticleMetadata(prefix="pmid", raw_id=raw_id, error=str(e), status_code=500)

class DoiClient(BaseClient):
    def __init__(self, settings: Settings):
        super().__init__(settings, rate=5.0, workers=5)

    def _fetch_single(self, raw_id: str) -> ArticleMetadata:
        self._wait_rate_limit()
        actual_doi = urllib.parse.unquote(raw_id)
        url = f"{self.settings.doi_api_base}{actual_doi}"
        headers = {"Accept": "application/vnd.citationstyles.csl+json"}
        if self.settings.email:
            headers["User-Agent"] = f"QuartoRef/{__version__} (mailto:{self.settings.email})"

        try:
            resp = self.session.get(url, headers=headers, timeout=self.settings.api_timeout, allow_redirects=True)
            if resp.status_code == 404:
                return ArticleMetadata(prefix="doi", raw_id=raw_id, error="Not found", status_code=404)
            resp.raise_for_status()

            try:
                return ArticleMetadata(prefix="doi", raw_id=raw_id, csl_data=resp.json())
            except Exception:
                return ArticleMetadata(prefix="doi", raw_id=raw_id, error="Metadata not available in CSL-JSON format", status_code=resp.status_code)
        except Exception as e:
            return ArticleMetadata(prefix="doi", raw_id=raw_id, error=str(e), status_code=500)

# ==========================================
# 🛠️ ユーティリティ
# ==========================================

def download_csl_style(style_name: str, repo_url: str) -> bool:
    """CSLファイルを自動取得"""
    if style_name.startswith(("http://", "https://")):
        return True
    if not style_name.endswith(".csl"):
        style_name += ".csl"
    dest_path = Path(style_name)
    if dest_path.exists():
        return True
    print(f"Downloading CSL style: {style_name}...")
    try:
        r = requests.get(repo_url + style_name, timeout=10)
        if r.status_code == 200:
            dest_path.write_text(r.text, encoding="utf-8")
            return True
    except Exception as e:
        print(f"Warning: Error downloading CSL: {e}")
    return False

def get_yaml_data(text: str) -> tuple[Any, str]:
    """YAMLフロントマターの解析"""
    yaml_match = re.match(r'^(---\n.*?\n---)', text, re.DOTALL)
    if not yaml_match:
        return None, ""
    yaml_raw = yaml_match.group(1)
    yaml_content = yaml_raw.strip('-').strip()
    yaml_obj = YAML()
    yaml_obj.preserve_quotes = True
    try:
        data = yaml_obj.load(yaml_content) or {}
        return data, yaml_raw
    except Exception:
        return None, yaml_raw

def normalize_markdown(text: str) -> tuple[str, list[tuple[str, str]]]:
    """タグの統合とIDの抽出"""
    def normalize_id(prefix: str, raw_id: str) -> str:
        clean_id = raw_id.strip()
        if prefix == "doi":
            clean_id = clean_id.rstrip(".,").lower()
        return clean_id

    def merge_tags(match):
        tags = RE_TAG_EXTRACT.findall(match.group(0))
        seen = set()
        unique_tags = []
        for prefix, raw_id in tags:
            clean_id = normalize_id(prefix, raw_id)
            tag_str = f"@{prefix}:{clean_id}"
            if tag_str not in seen:
                seen.add(tag_str)
                unique_tags.append(tag_str)
        return f"[{'; '.join(unique_tags)}]"

    text = RE_CONSECUTIVE.sub(merge_tags, text)

    def replace_tag_content(m):
        prefix, raw_id = m.groups()
        return f"@{prefix}:{normalize_id(prefix, raw_id)}"
    text = RE_TAG_EXTRACT.sub(replace_tag_content, text)

    all_found = RE_TAG_EXTRACT.findall(text)
    ids = []
    seen = set()
    for prefix, raw_id in all_found:
        if (prefix, raw_id) not in seen:
            seen.add((prefix, raw_id))
            ids.append((prefix, raw_id))
    return text, ids

def update_yaml_frontmatter(yaml_raw: str, body_text: str, bib_filename: str, yaml_data: dict) -> str:
    """YAMLにbibliographyを追記"""
    changed = False
    current_bib = yaml_data.get("bibliography")
    if current_bib is None:
        yaml_data["bibliography"] = bib_filename
        changed = True
    elif isinstance(current_bib, str):
        if current_bib != bib_filename:
            yaml_data["bibliography"] = [current_bib, bib_filename]
            changed = True
    elif isinstance(current_bib, list):
        if bib_filename not in current_bib:
            yaml_data["bibliography"].append(bib_filename)
            changed = True
    if not changed:
        return yaml_raw + body_text
    yaml_obj = YAML()
    yaml_obj.preserve_quotes = True
    buf = io.StringIO()
    yaml_obj.dump(yaml_data, buf)
    return f"---\n{buf.getvalue()}---{body_text}"

def _select_target_file() -> Path | None:
    """対象ファイルの選択"""
    cands = list(Path.cwd().glob("*.qmd")) + list(Path.cwd().glob("*.md"))
    if not cands:
        print("Error: No .qmd or .md files found.")
        return None
    if len(cands) == 1:
        print(f"Auto-selected: {cands[0].name}")
        return cands[0]
    print("\nSelect Target Document:")
    for i, f in enumerate(cands, 1):
        print(f"  {i}. {f.name}")
    while True:
        try:
            c = input("Select (number): ").strip()
            if c.isdigit() and 1 <= int(c) <= len(cands):
                return cands[int(c)-1]
        except (EOFError, KeyboardInterrupt):
            return None

# ==========================================
# 🚀 メイン処理
# ==========================================

def main() -> int:
    settings = Settings()
    parser = argparse.ArgumentParser(description=f"QuartoRef v{__version__} - PubMed & DOI Sync Tool")
    parser.add_argument("input_file", nargs="?", help="Input .qmd or .md file.")
    parser.add_argument("--update-yaml", action=argparse.BooleanOptionalAction, default=settings.update_yaml)
    parser.add_argument("--download-csl", action=argparse.BooleanOptionalAction, default=settings.download_csl)
    parser.add_argument("--api-key", help="NCBI API Key (Overrides Env/Dotenv)")
    parser.add_argument("--email", help="Email for DOI Polite Pool (Overrides Env/Dotenv)")
    args = parser.parse_args()

    if args.email:
        settings = replace(settings, email=args.email)
    if args.api_key:
        settings = replace(settings, api_key=args.api_key)

    in_path = Path(args.input_file) if args.input_file else _select_target_file()
    if not in_path or not in_path.exists():
        return 1

    original_text = in_path.read_text(encoding="utf-8")
    bib_path = in_path.with_suffix(".json")
    bib_filename = bib_path.name

    # 1. 正規化とID抽出
    processed_text, id_pairs = normalize_markdown(original_text)

    # 2. YAML解析とCSL自動ダウンロード
    yaml_data, yaml_raw = get_yaml_data(processed_text)
    if yaml_data and args.download_csl:
        csl_value = yaml_data.get("csl")
        if isinstance(csl_value, str):
            download_csl_style(csl_value, settings.csl_repo_url)

    # 3. YAML連携
    if args.update_yaml:
        if yaml_data is not None:
            body = processed_text[len(yaml_raw):]
            processed_text = update_yaml_frontmatter(yaml_raw, body, bib_filename, yaml_data)
        elif not yaml_raw:
            processed_text = f"---\nbibliography: {bib_filename}\n---\n\n{processed_text}"

    # 4. 文献データの同期
    existing_bib = {}
    if bib_path.exists():
        try:
            with open(bib_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                existing_bib = {str(item.get("id")): item for item in data if "id" in item}
        except Exception: pass

    to_fetch = []
    for prefix, clean_id in id_pairs:
        full_id = f"{prefix}:{clean_id}"
        if full_id not in existing_bib or existing_bib[full_id].get("title", "").startswith("[Error]"):
            to_fetch.append((prefix, clean_id))

    pm_client = PubMedClient(settings)
    doi_client = DoiClient(settings)
    
    if to_fetch:
        results: list[ArticleMetadata] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_id = {}
            for prefix, clean_id in to_fetch:
                client = pm_client if prefix == "pmid" else doi_client
                future = executor.submit(client._fetch_single, clean_id)
                future_to_id[future] = (prefix, clean_id)
            for future in concurrent.futures.as_completed(future_to_id):
                results.append(future.result())

        for meta in results:
            if meta.is_valid or meta.status_code == 404:
                existing_bib[meta.full_id] = meta.to_csl_json()
            else:
                print(f"Warning: [{meta.full_id}] Fetch failed ({meta.error})")
                existing_bib[meta.full_id] = meta.to_csl_json()

    # 全てのエントリを最新の正規化ロジックで再正規化して保存
    # (既存データに不正な形式が含まれている場合でもここで修正される)
    normalized_bib = {fid: ArticleMetadata.from_existing(csl).to_csl_json() 
                      for fid, csl in existing_bib.items()}
    
    # 実際に出力対象となるIDのみをフィルタリング (Markdown内で使われているものに限定したい場合はここで)
    # 現状はキャッシュとして全て保存する方針を維持
    
    if normalized_bib:
        # JSONが変更されたか、新規取得があった場合に書き出し
        # 簡易的に件数と全データの比較を行う
        export_list = sorted(normalized_bib.values(), key=lambda x: str(x.get("id", "")))
        
        # 既存のファイル内容と比較して変更がある場合のみ上書き
        should_write = True
        if bib_path.exists():
            try:
                with open(bib_path, "r", encoding="utf-8") as f:
                    if json.load(f) == export_list:
                        should_write = False
            except Exception: pass
            
        if should_write:
            with open(bib_path, "w", encoding="utf-8") as f:
                json.dump(export_list, f, ensure_ascii=False, indent=2)
            print(f"✓ Bibliography synced: {bib_filename} (Total: {len(export_list)})")
        else:
            if id_pairs: print("✓ All citations are up to date.")
    elif id_pairs:
        print("Warning: No citation data available.")

    # 5. 書き出し
    if processed_text != original_text:
        bak_path = in_path.with_suffix(in_path.suffix + ".bak")
        if not bak_path.exists() or bak_path.read_text(encoding="utf-8") != original_text:
            shutil.copy2(in_path, bak_path)
            print(f"✓ Backup created: {bak_path.name}")
        in_path.write_text(processed_text, encoding="utf-8")
        print(f"✓ Document updated: {in_path.name}")
    else:
        print("✓ No changes needed in the document.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
