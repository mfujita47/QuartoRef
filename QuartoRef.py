#!/usr/bin/env python3
"""
QuartoRef - Quarto-optimized PubMed & DOI Metadata Fetcher & Sync Tool

Description:
    .qmd / .md ファイル内の [@pmid:ID] および [@doi:ID] タグを検出し、
    APIから標準 CSL-JSON を取得して同名の CSL-JSON ファイルとして保存します。
"""
from __future__ import annotations

__version__ = "1.5.0"

import argparse
import io
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import requests
    from ruamel.yaml import YAML
    from dotenv import load_dotenv
except ImportError:
    print("Error: Required libraries are missing. Please run: pip install requests ruamel.yaml python-dotenv", file=sys.stderr)
    sys.exit(1)

load_dotenv(override=True)

# ==========================================
# ⚙️ 定数・正規表現定義
# ==========================================
CSL_STR_FIELDS = {"ISSN", "ISBN", "container-title", "container-title-short", "publisher"}
STANDARD_FIELDS = {
    "id", "type", "title", "author", "issued", "container-title",
    "container-title-short", "volume", "issue", "page", "DOI", "PMID",
    "URL", "ISSN", "ISBN", "publisher", "page-first", "language", "accessed", "abstract"
}

RE_TAG_EXTRACT = re.compile(r'@(?P<prefix>pmid|doi):(?P<id>[^;\]\s]+)', re.IGNORECASE)
RE_ONE_PASS = re.compile(r'(?P<block>\[@(?:pmid|doi):[^\]]+\](?:\s*\[@(?:pmid|doi):[^\]]+\])*)|(?P<tag>@(?:pmid|doi):[^;\]\s]+)', re.IGNORECASE)
RE_YAML_BLOCK = re.compile(r'^\s*---\r?\n(.*?)\r?\n---', re.DOTALL)

# ==========================================
# 📦 データモデル
# ==========================================

@dataclass(frozen=True)
class Settings:
    update_yaml: bool = True
    download_csl: bool = True
    ncbi_api_key: str | None = None
    email: str | None = None
    api_timeout: float = 20.0
    csl_repo_url: str = "https://raw.githubusercontent.com/citation-style-language/styles/master/"
    verbose: bool = True

@dataclass
class ArticleMetadata:
    full_id: str
    csl_data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    status_code: int = 200

    @property
    def is_valid(self) -> bool:
        return self.error is None and bool(self.csl_data)

# ==========================================
# 🔧 ユーティリティ
# ==========================================

def finalize_csl_item(meta: ArticleMetadata) -> dict[str, Any]:
    """Quartoの引用キーと一致させるための最小限の調整、またはエラーデータの生成"""
    if not meta.is_valid:
        return {
            "id": meta.full_id,
            "type": "article-journal",
            "title": f"[Error] Fetch failed ({meta.error})",
            "author": [{"family": meta.full_id.upper(), "given": ""}],
            "issued": {"date-parts": [[0]]}
        }

    # CSL-JSONの標準フィールドのみを抽出し、配列型の文字列フィールドを平滑化
    csl = {k: (", ".join(map(str, v)) if k in CSL_STR_FIELDS and isinstance(v, list) else v)
           for k, v in (meta.csl_data or {}).items() if k in STANDARD_FIELDS}

    # 必須プロパティの補正
    csl["id"] = meta.full_id

    # CSL-JSON規格に準拠させるための文献タイプのマッピング
    type_mappings = {
        "journal-article": "article-journal",
        "book-chapter": "chapter",
        "proceedings-article": "paper-conference"
    }
    csl["type"] = type_mappings.get(csl.get("type"), csl.get("type") or "article-journal")

    # container-title-short のピリオド除去とトリミング
    if "container-title-short" in csl and isinstance(csl["container-title-short"], str):
        csl["container-title-short"] = csl["container-title-short"].replace(".", "").strip()

    if "issued" not in csl:
        csl["issued"] = {"date-parts": [[0]]}
    if "author" not in csl:
        csl["author"] = [{"family": "UNKNOWN AUTHOR", "given": ""}]

    return csl

# ==========================================
# 🌐 外部連携 (Network/IO)
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

def fetch_citation(prefix: str, raw_id: str, settings: Settings) -> ArticleMetadata:
    full_id = f"{prefix}:{raw_id}"
    headers = {"User-Agent": f"QuartoRef/{__version__} (mailto:{settings.email})"} if settings.email else {"User-Agent": f"QuartoRef/{__version__}"}

    # プレフィックスによる分岐（エンドポイントとパラメータの切り替えのみ）
    if prefix == "pmid":
        url = "https://pmc.ncbi.nlm.nih.gov/api/ctxp/v1/pubmed/"
        params = {"format": "csl", "id": raw_id}
        if settings.ncbi_api_key:
            params["api_key"] = settings.ncbi_api_key
    elif prefix == "doi":
        url = "https://citation.doi.org/metadata"
        params = {"doi": raw_id}
    else:
        return ArticleMetadata(full_id=full_id, error=f"Unsupported prefix: {prefix}", status_code=400)

    # 共通の通信処理
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=settings.api_timeout)
        resp.raise_for_status()
        return ArticleMetadata(full_id=full_id, csl_data=resp.json())
    except requests.exceptions.RequestException as e:
        status = e.response.status_code if e.response is not None else 500
        error_msg = "Not found" if status == 404 else str(e)
        return ArticleMetadata(full_id=full_id, error=error_msg, status_code=status)

# ==========================================
# 📝 ドキュメント処理 (Core Logic)
# ==========================================

def process_markdown_content(text: str) -> tuple[str, dict[str, tuple[str, str]]]:
    found_ids: dict[str, tuple[str, str]] = {}

    def process_match(m: re.Match) -> str:
        text_chunk = m.group("block") or m.group("tag")
        tags = []
        for p, r in RE_TAG_EXTRACT.findall(text_chunk):
            p_low = p.lower()
            clean_id = r.strip().rstrip(".,").lower()
            full_tag = f"{p_low}:{clean_id}"
            found_ids[full_tag] = (p_low, clean_id)
            tags.append(f"@{full_tag}")

        return f"[{';'.join(dict.fromkeys(tags))}]"

    processed = RE_ONE_PASS.sub(process_match, text)
    return processed, found_ids

def process_yaml_frontmatter(text: str, bib_filename: str, settings: Settings) -> str:
    yaml_match = RE_YAML_BLOCK.search(text)

    if not yaml_match:
        if settings.update_yaml:
            return f"---\nbibliography: {bib_filename}\n---\n\n{text}"
        return text

    parser = YAML()
    parser.preserve_quotes = True
    parser.explicit_start = True
    parser.explicit_end = False
    try:
        data = parser.load(yaml_match.group(1))
        if not isinstance(data, dict): data = {}
    except Exception as e:
        print(f"Warning: Failed to parse YAML frontmatter. ({e})", file=sys.stderr)
        return text

    modified = False
    if settings.download_csl and (csl_val := data.get("csl")):
        download_csl_style(str(csl_val), settings.csl_repo_url)

    if settings.update_yaml:
        bibs_raw = data.get("bibliography") or []
        bibs = [str(b) for b in (bibs_raw if isinstance(bibs_raw, list) else [bibs_raw]) if b]
        if bib_filename not in bibs:
            bibs.append(bib_filename)
            data["bibliography"] = bibs[0] if len(bibs) == 1 else bibs
            modified = True

    if modified:
        buf = io.StringIO()
        parser.dump(data, buf)
        yaml_output = buf.getvalue().strip()
        return RE_YAML_BLOCK.sub(f"{yaml_output}\n---", text, count=1)

    return text

# ==========================================
# 🚀 実行制御層
# ==========================================

def _select_target_file() -> Path | None:
    cands = sorted(list(Path.cwd().glob("*.qmd")) + list(Path.cwd().glob("*.md")))
    if not cands: return None
    if len(cands) == 1: return cands[0]

    print("\nSelect Target Document:", file=sys.stderr)
    for i, f in enumerate(cands, 1): print(f"  {i}. {f.name}", file=sys.stderr)
    try:
        c = input("Select (number): ").strip()
        if c.isdigit() and 1 <= int(c) <= len(cands): return cands[int(c)-1]
    except (KeyboardInterrupt, EOFError):
        print("\nOperation cancelled by user.", file=sys.stderr)
        sys.exit(0)
    return None

def main() -> int:
    parser = argparse.ArgumentParser(description=f"QuartoRef v{__version__}")
    parser.add_argument("input_file", nargs="?", help="Input .qmd or .md file.")
    parser.add_argument("--update-yaml", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--download-csl", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    in_path = Path(args.input_file) if args.input_file else _select_target_file()
    if not in_path or not in_path.is_file():
        print("Error: Valid input file not found.", file=sys.stderr)
        return 1

    settings = Settings(
        update_yaml=args.update_yaml,
        download_csl=args.download_csl,
        ncbi_api_key=os.getenv("NCBI_API_KEY"),
        email=os.getenv("EMAIL"),
        verbose=args.verbose
    )

    if settings.ncbi_api_key and settings.verbose:
        key = settings.ncbi_api_key
        masked = key[:4] + "..." + key[-4:] if len(key) > 8 else "..."
        print(f"✓ Loaded NCBI API Key: {masked}", file=sys.stderr)

    try:
        original_text = in_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error: Cannot read file {in_path.name}. ({e})", file=sys.stderr)
        return 1

    bib_path = in_path.with_suffix(".json")
    processed_text, found_ids = process_markdown_content(original_text)
    processed_text = process_yaml_frontmatter(processed_text, bib_path.name, settings)

    existing_bib: dict[str, Any] = {}
    pruned = False
    if bib_path.exists():
        try:
            full_existing = {str(i["id"]).lower(): i for i in json.loads(bib_path.read_text(encoding="utf-8")) if i.get("id")}
            existing_bib = {k: v for k, v in full_existing.items() if k in found_ids}
            if len(existing_bib) < len(full_existing): pruned = True
        except Exception:
            print(f"Warning: {bib_path.name} is corrupted. Rebuilding...", file=sys.stderr)

    to_fetch = [(p, r) for full_id, (p, r) in found_ids.items() if full_id not in existing_bib or "[Error]" in existing_bib[full_id].get("title", "")]

    if to_fetch or pruned:
        if to_fetch:
            total = len(to_fetch)
            if settings.verbose:
                print(f"Fetching {total} new citation{'s' if total > 1 else ''}...", file=sys.stderr)
            for idx, (p, r) in enumerate(to_fetch, 1):
                full_id = f"{p}:{r}"
                if settings.verbose:
                    print(f"[{idx}/{total}] Fetching {full_id}...", end="", flush=True, file=sys.stderr)
                if idx > 1:
                    time.sleep(1.0)
                meta = fetch_citation(p, r, settings)
                existing_bib[meta.full_id] = finalize_csl_item(meta)
                if settings.verbose:
                    res = f" Success: {existing_bib[meta.full_id].get('title', '')[:50]}..." if meta.is_valid else f" Failed ({meta.error})"
                    print(res, file=sys.stderr)

        export_list = sorted(existing_bib.values(), key=lambda x: x.get("id", ""))
        try:
            bib_path.write_text(json.dumps(export_list, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"✓ Bibliography synced: {bib_path.name} (Total: {len(export_list)})")
        except OSError as e:
            print(f"Error: Failed to save bibliography {bib_path.name}. ({e})", file=sys.stderr)
            return 1
    elif found_ids:
        print("✓ All citations are already cached.")

    if processed_text != original_text:
        bak_path = in_path.with_suffix(in_path.suffix + ".bak")
        try:
            bak_path.write_text(original_text, encoding="utf-8")
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
