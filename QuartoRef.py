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

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    from ruamel.yaml import YAML
    from dotenv import load_dotenv
except ImportError:
    print("Error: Required libraries are missing. Please run: pip install requests ruamel.yaml python-dotenv", file=sys.stderr)
    sys.exit(1)

load_dotenv(override=False)

# YAMLパーサーの共通設定
yaml_parser = YAML()
yaml_parser.preserve_quotes = True
yaml_parser.explicit_start = True
yaml_parser.explicit_end = False

# ==========================================
# ⚙️ 定数定義
# ==========================================
CSL_STR_FIELDS = ["ISSN", "ISBN", "container-title", "container-title-short", "publisher"]
STANDARD_FIELDS = {
    "id", "type", "title", "author", "issued", "container-title",
    "container-title-short", "volume", "issue", "page", "DOI", "PMID",
    "URL", "ISSN", "ISBN", "publisher", "abstract", "page-first",
    "journal-abbreviation", "language", "accessed"
}

# 🔍 正規表現パターン (Smart Merging 用)
RE_TAG_PATTERN = r'@(?P<prefix>pmid|doi):(?P<id>[^;\]\s]+)'
RE_TAG_EXTRACT = re.compile(RE_TAG_PATTERN)
RE_BLOCK = r'\[@(?:pmid|doi):[^\]]+\]'
RE_ONE_PASS = re.compile(f'(?P<block>{RE_BLOCK}(?:\\s*{RE_BLOCK})*)|(?P<tag>{RE_TAG_PATTERN})')

# ==========================================
# 📦 データモデル & ロジック
# ==========================================

@dataclass(frozen=True)
class Settings:
    update_yaml: bool = True
    download_csl: bool = True
    api_key: str | None = None
    email: str | None = None
    api_timeout: float = 20.0
    csl_repo_url: str = "https://raw.githubusercontent.com/citation-style-language/styles/master/"

@dataclass
class ArticleMetadata:
    full_id: str
    csl_data: dict = field(default_factory=dict)
    error: str | None = None
    status_code: int = 200

    @property
    def is_valid(self) -> bool:
        return self.error is None and bool(self.csl_data)

def clean_csl_item(meta: ArticleMetadata) -> dict[str, Any]:
    """メタデータを標準形式の CSL-JSON 辞書に変換"""
    raw = meta.csl_data or {}
    csl = {k: (", ".join(map(str, v)) if k in CSL_STR_FIELDS and isinstance(v, list) else v)
           for k, v in raw.items() if k in STANDARD_FIELDS}

    csl["id"] = meta.full_id
    csl.setdefault("type", "article-journal")
    csl.setdefault("title", f"[Error] {meta.error}" if meta.error else f"[{meta.full_id}] Title missing")
    csl.setdefault("issued", {"date-parts": [[0]]})

    if "author" not in csl:
        parts = meta.full_id.split(":", 1)
        p_str, r_str = (parts[0].upper(), parts[1]) if len(parts) == 2 else ("UNKNOWN", meta.full_id)
        csl["author"] = [{"family": f"{p_str} {r_str}".strip(), "given": ""}]
    return csl

def process_markdown_content(text: str) -> tuple[str, list[tuple[str, str]]]:
    """本文の正規化とID抽出（副作用を抑えた設計）"""
    found_ids: dict[str, tuple[str, str]] = {}

    def _format_tag(prefix: str, raw_id: str) -> tuple[str, str]:
        prefix = prefix.lower()
        clean_id = raw_id.strip().rstrip(".,")
        if prefix == "doi": clean_id = clean_id.lower()
        return prefix, clean_id

    def process_match(m: re.Match) -> str:
        if m.group("block"):
            tags = RE_TAG_EXTRACT.findall(m.group("block"))
            unique_formatted_tags = []
            for p, r in tags:
                prefix, clean_id = _format_tag(p, r)
                full_tag = f"{prefix}:{clean_id}"
                found_ids[full_tag] = (prefix, clean_id)
                unique_formatted_tags.append(f"@{full_tag}")

            # 重複除去を維持しつつ結合
            return f"[{'; '.join(dict.fromkeys(unique_formatted_tags))}]"

        # 単一タグ (@tag) -> [ @tag ] へ正規化
        prefix, clean_id = _format_tag(m.group('prefix'), m.group('id'))
        full_tag = f"{prefix}:{clean_id}"
        found_ids[full_tag] = (prefix, clean_id)
        return f"[@{full_tag}]"

    processed = RE_ONE_PASS.sub(process_match, text)
    return processed, list(found_ids.values())

def inject_yaml_bibliography(text: str, bib_filename: str) -> str:
    """YAMLフロントマターに bibliography を安全に挿入/更新"""
    yaml_match = re.match(r'^---\r?\n(.*?)\r?\n---', text, re.DOTALL)
    if not yaml_match:
        return f"---\nbibliography: {bib_filename}\n---\n\n{text}"

    yaml_raw_content = yaml_match.group(1)
    try:
        data = yaml_parser.load(yaml_raw_content) or {}
    except Exception:
        return text

    # YAMLの値がどんな型で入ってくるか分からないための安全なリスト化
    bibs_raw = data.get("bibliography")
    if bibs_raw is None:
        bibs = []
    elif isinstance(bibs_raw, list):
        bibs = [str(b) for b in bibs_raw]
    elif isinstance(bibs_raw, str):
        bibs = [bibs_raw]
    else:
        bibs = [str(bibs_raw)]

    if bib_filename not in bibs:
        bibs.append(bib_filename)
        data["bibliography"] = bibs[0] if len(bibs) == 1 else bibs

        buf = io.StringIO()
        yaml_parser.dump(data, buf)
        new_yaml = f"---\n{buf.getvalue().strip()}\n---"
        return re.sub(r'^---\r?\n.*?\r?\n---', new_yaml, text, count=1, flags=re.DOTALL)
    return text

# ==========================================
# 🌐 API クライアント (統合)
# ==========================================

class CitationAPIClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.locks = {"pmid": threading.Lock(), "doi": threading.Lock()}
        self.next_calls = {"pmid": 0.0, "doi": 0.0}
        self.rates = {"pmid": 9.0 if settings.api_key else 3.0, "doi": 5.0}

        self.session = requests.Session()
        retry = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def _wait_for_rate(self, prefix: str):
        with self.locks[prefix]:
            now = time.time()
            wait_time = max(0.0, self.next_calls[prefix] - now)
            self.next_calls[prefix] = now + wait_time + (1.0 / self.rates[prefix])
        if wait_time > 0: time.sleep(wait_time)

    def fetch(self, prefix: str, raw_id: str) -> ArticleMetadata:
        self._wait_for_rate(prefix)
        full_id = f"{prefix}:{raw_id}"
        try:
            if prefix == "pmid":
                url = "https://pmc.ncbi.nlm.nih.gov/api/ctxp/v1/pubmed/"
                params = {"format": "csl", "id": raw_id} | ({"api_key": self.settings.api_key} if self.settings.api_key else {})
                resp = self.session.get(url, params=params, timeout=self.settings.api_timeout)
            else:
                url = f"https://doi.org/{urllib.parse.unquote(raw_id)}"
                headers = {"Accept": "application/vnd.citationstyles.csl+json"}
                if self.settings.email: headers["User-Agent"] = f"QuartoRef/{__version__} (mailto:{self.settings.email})"
                resp = self.session.get(url, headers=headers, timeout=self.settings.api_timeout)

            if resp.status_code == 404: return ArticleMetadata(full_id=full_id, error="Not found", status_code=404)

            resp.raise_for_status()
            return ArticleMetadata(full_id=full_id, csl_data=resp.json())

        except requests.exceptions.HTTPError as e:
            # 💡 改善: 詳細なHTTPステータスコードを捕捉
            status = e.response.status_code if e.response is not None else 500
            return ArticleMetadata(full_id=full_id, error=str(e), status_code=status)
        except Exception as e:
            return ArticleMetadata(full_id=full_id, error=str(e), status_code=500)

# ==========================================
# 🚀 実行・I/O層
# ==========================================

def download_csl_style(style_name: str, repo_url: str) -> bool:
    if style_name.startswith(("http://", "https://")): return True
    safe_name = Path(style_name).name
    if not safe_name.endswith(".csl"):
        safe_name += ".csl"

    dest_path = Path.cwd() / safe_name
    if dest_path.exists(): return True

    print(f"Downloading CSL style: {safe_name}...", file=sys.stderr)
    try:
        r = requests.get(repo_url + safe_name, timeout=10)
        if r.status_code == 200:
            dest_path.write_text(r.text, encoding="utf-8")
            return True
    except Exception as e:
        print(f"Warning: Error downloading CSL: {e}", file=sys.stderr)
    return False

def _select_target_file() -> Path | None:
    cands = sorted(itertools.chain(Path.cwd().glob("*.qmd"), Path.cwd().glob("*.md")))
    if not cands: return None
    if len(cands) == 1: return cands[0]

    print("\nSelect Target Document:", file=sys.stderr)
    for i, f in enumerate(cands, 1): print(f"  {i}. {f.name}", file=sys.stderr)
    try:
        c = input("Select (number): ").strip()
        if c.isdigit() and 1 <= int(c) <= len(cands): return cands[int(c)-1]
    except KeyboardInterrupt:
        # 💡 改善: Ctrl+C を明示的なキャンセルとして扱い、プロセスを正常終了させる
        print("\nOperation cancelled by user.", file=sys.stderr)
        sys.exit(0)
    except EOFError:
        pass
    return None

def main() -> int:
    parser = argparse.ArgumentParser(description=f"QuartoRef v{__version__}")
    parser.add_argument("input_file", nargs="?", help="Input .qmd or .md file.")
    parser.add_argument("--update-yaml", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--download-csl", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    in_path = Path(args.input_file) if args.input_file else _select_target_file()
    if not in_path or not in_path.is_file():
        print("Error: Valid input file not found.", file=sys.stderr)
        return 1

    settings = Settings(
        update_yaml=args.update_yaml,
        download_csl=args.download_csl,
        api_key=os.getenv("NCBI_API_KEY"),
        email=os.getenv("EMAIL")
    )

    try:
        original_text = in_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print(f"Error: {in_path.name} is not a valid UTF-8 encoded file.", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Error: Cannot read file {in_path.name}. ({e})", file=sys.stderr)
        return 1

    bib_path = in_path.with_suffix(".json")

    # 1. コンテンツ処理
    processed_text, id_pairs = process_markdown_content(original_text)

    if settings.download_csl:
        yaml_match = re.match(r'^---\r?\n(.*?)\r?\n---', processed_text, re.DOTALL)
        if yaml_match:
            try:
                yaml_data = yaml_parser.load(yaml_match.group(1)) or {}
                if csl_val := yaml_data.get("csl"):
                    download_csl_style(str(csl_val), settings.csl_repo_url)
            except Exception as e:
                print(f"Warning: Failed to parse YAML for CSL downloading. ({e})", file=sys.stderr)

    if settings.update_yaml:
        processed_text = inject_yaml_bibliography(processed_text, bib_path.name)

    # 2. キャッシュ同期
    existing_bib: dict[str, Any] = {}
    if bib_path.exists():
        try:
            existing_bib = {str(i["id"]): i for i in json.loads(bib_path.read_text(encoding="utf-8")) if i.get("id")}
        except Exception:
            print(f"Warning: {bib_path.name} is corrupted or invalid JSON. Rebuilding...", file=sys.stderr)

    to_fetch = [(p, r) for p, r in id_pairs if f"{p}:{r}" not in existing_bib or "[Error]" in existing_bib[f"{p}:{r}"].get("title", "")]

    if to_fetch:
        client = CitationAPIClient(settings)
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(client.fetch, p, r) for p, r in to_fetch]
            for future in concurrent.futures.as_completed(futures):
                meta = future.result()
                existing_bib[meta.full_id] = clean_csl_item(meta)
                if not meta.is_valid:
                    print(f"Warning: [{meta.full_id}] Fetch failed (HTTP {meta.status_code}: {meta.error})", file=sys.stderr)

        export_list = sorted(existing_bib.values(), key=lambda x: str(x.get("id", "")))
        try:
            bib_path.write_text(json.dumps(export_list, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"✓ Bibliography synced: {bib_path.name} (Total: {len(export_list)})")
        except OSError as e:
            print(f"Error: Failed to save bibliography {bib_path.name}. ({e})", file=sys.stderr)
            return 1
    elif id_pairs:
        print("✓ All citations are already cached.")

    # 3. 保存
    if processed_text != original_text:
        bak_path = in_path.with_suffix(in_path.suffix + ".bak")
        try:
            shutil.copy2(in_path, bak_path)
            in_path.write_text(processed_text, encoding="utf-8")
            print(f"✓ Backup created: {bak_path.name}\n✓ Document updated: {in_path.name}")
        except OSError as e:
            print(f"Error: Failed to update document {in_path.name}. ({e})", file=sys.stderr)
            return 1
    else:
        print("✓ No changes needed in the document.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
