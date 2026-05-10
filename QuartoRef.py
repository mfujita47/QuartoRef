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
import itertools
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
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

# YAMLパーサーの共通インスタンス (初期化コスト削減)
yaml_parser = YAML()
yaml_parser.preserve_quotes = True
yaml_parser.explicit_start = True
yaml_parser.explicit_end = False

# ==========================================
# ⚙️ 定数定義
# ==========================================
# CSL-JSON において文字列に正規化すべきフィールド
CSL_STR_FIELDS = ["ISSN", "ISBN", "container-title", "container-title-short", "publisher"]

# Pandoc/Quarto がサポートする標準的な CSL-JSON フィールド
STANDARD_FIELDS = {
    "id", "type", "title", "author", "issued", "container-title", 
    "container-title-short", "volume", "issue", "page", "DOI", "PMID", 
    "URL", "ISSN", "ISBN", "publisher", "abstract", "page-first", 
    "journal-abbreviation", "language", "accessed"
}

# ==========================================
# ⚙️ ユーザー設定
# ==========================================
@dataclass(frozen=True)
class Settings:
    update_yaml: bool = True
    download_csl: bool = True
    pubmed_api_base: str = "https://pmc.ncbi.nlm.nih.gov/api/ctxp/v1/pubmed/"
    doi_api_base: str = "https://doi.org/"
    api_key: str | None = None
    email: str | None = None
    api_timeout: float = 20.0
    csl_repo_url: str = "https://raw.githubusercontent.com/citation-style-language/styles/master/"

# ==========================================
# 🔍 正規表現パターン
# ==========================================
# 単一の引用タグ [@prefix:ID]
RE_TAG_PATTERN = r'@(pmid|doi):([^;\]\s]+)'
RE_TAG_EXTRACT = re.compile(RE_TAG_PATTERN)

# 括弧付き引用ブロック [@pmid:1] [@doi:10.123/abc]
RE_BLOCK = r'\[@(?:pmid|doi):[^\]]+\]'

# ワンパス走査用: グループ1=括弧付きブロック(連続対応), グループ3,4=裸のタグ
RE_ONE_PASS = re.compile(f'({RE_BLOCK}(?:\\s*{RE_BLOCK})*)|({RE_TAG_PATTERN})')

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
    def error_result(cls, prefix: str, raw_id: str, error_msg: str, status: int = 500) -> ArticleMetadata:
        """エラー結果を生成するファクトリメソッド"""
        return cls(prefix=prefix, raw_id=raw_id, error=error_msg, status_code=status)

    @property
    def full_id(self) -> str:
        """JSON内やMarkdown内で使用する一意のID (例: doi:10.123/abc%3Bdef)"""
        return f"{self.prefix}:{self.raw_id}"

    @property
    def is_valid(self) -> bool:
        return self.error is None and bool(self.csl_data)

    def to_csl_json(self) -> dict[str, Any]:
        """CSL-JSON形式のデータを正規化して、Pandoc互換の標準フィールドのみを返す"""
        return _clean_csl_item(
            self.csl_data or {}, 
            self.full_id, 
            error_msg=self.error,
            raw_id=self.raw_id,
            prefix=self.prefix
        )

def _normalize_csl_fields(csl_dict: dict) -> dict:
    """CSL-JSON 項目を標準フィールドでフィルタし、配列を文字列に正規化する共通処理"""
    filtered = {k: v for k, v in csl_dict.items() if k in STANDARD_FIELDS}
    for field_name in CSL_STR_FIELDS:
        val = filtered.get(field_name)
        if isinstance(val, list):
            # 空リストの join は "" になる
            filtered[field_name] = ", ".join(map(str, val))
    return filtered

def _clean_csl_item(raw: dict, full_id: str, error_msg: str | None = None, raw_id: str = "", prefix: str = "") -> dict:
    """CSL-JSON 項目を Pandoc/Quarto 互換の標準形式に整形する"""
    csl = _normalize_csl_fields(raw)
    csl["id"] = full_id

    # 必須フィールドの補完
    if not csl.get("type"):
        csl["type"] = "article-journal"

    if not csl.get("title"):
        csl["title"] = f"[Error] {error_msg}" if error_msg else f"[{full_id}] Title missing"

    if not csl.get("author"):
        # プレフィックスとIDが不明な場合はIDから推測
        p_str, r_str = (prefix.upper(), raw_id) if prefix else full_id.split(":", 1)
        csl["author"] = [{"family": f"{p_str} {r_str}", "given": ""}]

    if not csl.get("issued"):
        csl["issued"] = {"date-parts": [[0]]}

    return csl

# ==========================================
# 🌐 API クライアント
# ==========================================

class BaseClient:
    def __init__(self, settings: Settings, rate: float):
        self.settings = settings
        self.rate = rate
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

    def request_csl(self, url: str, params: dict | None = None, headers: dict | None = None) -> dict | str:
        """APIリクエストを実行し、JSONデータまたはエラーメッセージを返す"""
        self._wait_rate_limit()
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=self.settings.api_timeout, allow_redirects=True)
            if resp.status_code == 404:
                return "Not found"
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return str(e)

class PubMedClient(BaseClient):
    def __init__(self, settings: Settings):
        super().__init__(settings, rate=9.0 if settings.api_key else 3.0)

    def _fetch_single(self, raw_id: str) -> ArticleMetadata:
        params = {"format": "csl", "id": raw_id}
        if self.settings.api_key:
            params["api_key"] = self.settings.api_key
        
        result = self.request_csl(self.settings.pubmed_api_base, params=params)
        
        if isinstance(result, dict):
            return ArticleMetadata(prefix="pmid", raw_id=raw_id, csl_data=result)
        else:
            status = 404 if result == "Not found" else 500
            return ArticleMetadata.error_result("pmid", raw_id, result, status)

class DoiClient(BaseClient):
    def __init__(self, settings: Settings):
        super().__init__(settings, rate=5.0)

    def _fetch_single(self, raw_id: str) -> ArticleMetadata:
        actual_doi = urllib.parse.unquote(raw_id)
        url = f"{self.settings.doi_api_base}{actual_doi}"
        headers = {"Accept": "application/vnd.citationstyles.csl+json"}
        if self.settings.email:
            headers["User-Agent"] = f"QuartoRef/{__version__} (mailto:{self.settings.email})"

        result = self.request_csl(url, headers=headers)
        
        if isinstance(result, dict):
            return ArticleMetadata(prefix="doi", raw_id=raw_id, csl_data=result)
        else:
            status = 404 if result == "Not found" else 500
            return ArticleMetadata.error_result("doi", raw_id, result, status)

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

def get_yaml_data(text: str) -> tuple[dict[str, Any] | None, str]:
    """YAMLフロントマターの解析"""
    yaml_match = re.match(r'^(---\r?\n.*?\r?\n---)', text, re.DOTALL)
    if not yaml_match:
        return None, ""
    yaml_raw = yaml_match.group(1)
    yaml_content = yaml_raw.strip('-').strip()
    try:
        data = yaml_parser.load(yaml_content) or {}
        return data, yaml_raw
    except Exception:
        return None, yaml_raw

def normalize_markdown(text: str) -> tuple[str, list[tuple[str, str]]]:
    """タグの統合とIDの抽出（ワンパス走査）"""
    found_ids = {}

    def format_clean_id(prefix: str, raw_id: str) -> str:
        """IDのクリーニングと正規化"""
        clean_id = raw_id.strip().rstrip(".,")
        return clean_id.lower() if prefix == "doi" else clean_id

    def process_match(m):
        # 1. 連続ブロックまたは単一の括弧付きタグ [@pmid:1][@pmid:2]
        if m.group(1):
            tags = RE_TAG_EXTRACT.findall(m.group(1))
            # 順序を保ったまま重複排除 (dict.fromkeys で意図を明確化)
            for prefix, raw_id in tags:
                clean_id = format_clean_id(prefix, raw_id)
                found_ids[f"{prefix}:{clean_id}"] = (prefix, clean_id)
            unique_keys = dict.fromkeys(f"@{p}:{format_clean_id(p, r)}" for p, r in tags)
            return f"[{'; '.join(unique_keys)}]"
        
        # 2. 裸のタグ @pmid:1
        prefix, raw_id = m.group(3), m.group(4)
        clean_id = format_clean_id(prefix, raw_id)
        full_tag = f"{prefix}:{clean_id}"
        found_ids[full_tag] = (prefix, clean_id)
        return f"@{full_tag}"

    text = RE_ONE_PASS.sub(process_match, text)

    return text, list(found_ids.values())

def update_yaml_frontmatter(yaml_raw: str, body_text: str, bib_filename: str, yaml_data: dict) -> str:
    """YAMLにbibliographyを追記"""
    bibs = yaml_data.get("bibliography", [])
    if isinstance(bibs, str):
        bibs = [bibs]
    
    if bib_filename not in bibs:
        bibs.append(bib_filename)
        yaml_data["bibliography"] = bibs[0] if len(bibs) == 1 else bibs
        
        buf = io.StringIO()
        yaml_parser.dump(yaml_data, buf)

        # ruamel.yamlが出力した末尾の改行を削除し、明示的に --- を付与
        res_yaml = buf.getvalue().rstrip()
        return f"{res_yaml}\n---\n\n{body_text.lstrip()}"
    return yaml_raw + body_text

def _select_target_file() -> Path | None:
    """対象ファイルの選択"""
    cands = list(itertools.chain(Path.cwd().glob("*.qmd"), Path.cwd().glob("*.md")))
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
    parser = argparse.ArgumentParser(description=f"QuartoRef v{__version__} - PubMed & DOI Sync Tool")
    parser.add_argument("input_file", nargs="?", help="Input .qmd or .md file.")
    parser.add_argument("--update-yaml", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--download-csl", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--api-key", help="NCBI API Key (Overrides Env/Dotenv)")
    parser.add_argument("--email", help="Email for DOI Polite Pool (Overrides Env/Dotenv)")
    args = parser.parse_args()

    # CLI引数 → 環境変数 → デフォルト値 の優先順位で設定を構築
    settings = Settings(
        update_yaml=args.update_yaml if args.update_yaml is not None else Settings.update_yaml,
        download_csl=args.download_csl if args.download_csl is not None else Settings.download_csl,
        api_key=args.api_key or os.getenv("NCBI_API_KEY"),
        email=args.email or os.getenv("EMAIL")
    )

    in_path = Path(args.input_file) if args.input_file else _select_target_file()
    if not in_path or not in_path.exists():
        print("Error: Input path does not exist.")
        return 1
    if not in_path.is_file():
        print("Error: Input path is not a file.")
        return 1

    original_text = in_path.read_text(encoding="utf-8")
    bib_path = in_path.with_suffix(".json")
    bib_filename = bib_path.name

    # 1. 正規化とID抽出
    processed_text, id_pairs = normalize_markdown(original_text)

    # 2. YAML解析とCSL自動ダウンロード
    yaml_data, yaml_raw = get_yaml_data(processed_text)
    if yaml_data and settings.download_csl:
        csl_value = yaml_data.get("csl")
        if isinstance(csl_value, str):
            download_csl_style(csl_value, settings.csl_repo_url)

    # 3. YAML連携
    if settings.update_yaml:
        if yaml_data is not None:
            processed_text = update_yaml_frontmatter(yaml_raw, processed_text[len(yaml_raw):], bib_filename, yaml_data)
        elif yaml_raw:
            print(f"Warning: YAML frontmatter detected in {in_path.name} but could not be parsed. Skipping bibliography integration.")
        else:
            processed_text = f"---\nbibliography: {bib_filename}\n---\n\n{processed_text}"

    # 4. 文献データの同期
    existing_bib = {}
    if bib_path.exists():
        try:
            data = json.loads(bib_path.read_text(encoding="utf-8"))
            # idが存在し、かつ空でない場合のみ抽出
            existing_bib = {str(item_id): item for item in data if (item_id := item.get("id"))}
        except json.JSONDecodeError:
            print(f"Warning: The format of existing {bib_filename} is invalid. Skipping load.")
        except Exception as e:
            print(f"Warning: An error occurred while loading {bib_filename}: {e}")

    to_fetch = []
    for prefix, clean_id in id_pairs:
        full_id = f"{prefix}:{clean_id}"
        if full_id not in existing_bib or existing_bib[full_id].get("title", "").startswith("[Error]"):
            to_fetch.append((prefix, clean_id))

    if to_fetch:
        # 必要なクライアントのみを初期化
        clients = {}
        prefixes = {prefix for prefix, _ in to_fetch}
        if "pmid" in prefixes:
            clients["pmid"] = PubMedClient(settings)
        if "doi" in prefixes:
            clients["doi"] = DoiClient(settings)

        results: list[ArticleMetadata] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # タスクの追加もジェネレータ式で簡潔に
            futures = (
                executor.submit(clients[prefix]._fetch_single, clean_id)
                for prefix, clean_id in to_fetch
            )
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        for meta in results:
            if not meta.is_valid and meta.status_code != 404:
                print(f"Warning: [{meta.full_id}] Fetch failed ({meta.error})")
            existing_bib[meta.full_id] = meta.to_csl_json()

    # 既存のキャッシュも含めて再度正規化を適用 (Pandoc互換性のため)
    bib_changed = False
    for full_id, item in list(existing_bib.items()):
        normalized = _normalize_csl_fields(item)
        if normalized != item:
            existing_bib[full_id] = normalized
            bib_changed = True

    if to_fetch or bib_changed:
        export_list = sorted(existing_bib.values(), key=lambda x: str(x.get("id", "")))
        bib_path.write_text(json.dumps(export_list, ensure_ascii=False, indent=2), encoding="utf-8")
        
        if to_fetch:
            print(f"✓ Bibliography synced: {bib_filename} (Total: {len(export_list)})")
        elif bib_changed:
            print(f"✓ Bibliography format updated: {bib_filename}")
    else:
        if id_pairs: print("✓ All citations are already cached.")

    # 5. 書き出し
    if processed_text != original_text:
        # 変更がある場合のみバックアップを作成
        bak_path = in_path.with_suffix(in_path.suffix + ".bak")
        shutil.copy2(in_path, bak_path)
        print(f"✓ Backup created: {bak_path.name}")
        
        in_path.write_text(processed_text, encoding="utf-8")
        print(f"✓ Document updated: {in_path.name}")
    else:
        print("✓ No changes needed in the document.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
