#!/usr/bin/env python3
"""
QuartoPmid - Quarto-optimized PubMed Metadata Fetcher & Sync Tool

Description:
    .qmd / .md ファイル内の連続するPMIDタグ [@123] [@456] を [@123; @456] に統合し、
    NCBI APIから書誌情報を取得して同名の CSL-JSON ファイルとして保存します。
    QuartoのYAMLフロントマターと安全に連携し、必要なCSLスタイルを自動でダウンロードします。
"""
from __future__ import annotations

__version__ = "1.1.0"

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 外部ライブラリのチェック
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    from ruamel.yaml import YAML
except ImportError:
    print("Error: Required libraries are missing. Please run: pip install requests ruamel.yaml")
    sys.exit(1)

# 正規表現パターン
# 連続する [@123] [@456] ブロックを検出 (改行やスペースを許容)
RE_CONSECUTIVE = re.compile(r'(\[@\d+(?:;\s*@\d+)*\])(?:\s*\[@\d+(?:;\s*@\d+)*\])+')
# 全ての有効なPMIDを抽出
RE_PMID_EXTRACT = re.compile(r'@(\d+)')

PMID = str

# ==========================================
# ⚙️ ユーザー設定 (デフォルトの動作をここで制御できます)
# ==========================================
@dataclass(frozen=True)
class Settings:
    update_yaml: bool = True
    download_csl: bool = True
    api_base_url: str = "https://pmc.ncbi.nlm.nih.gov/api/ctxp/v1/pubmed/"
    api_key: str | None = field(default_factory=lambda: os.getenv("NCBI_API_KEY"))
    api_timeout: float = 20.0
    csl_repo_url: str = "https://raw.githubusercontent.com/citation-style-language/styles/master/"
# ==========================================

@dataclass
class ArticleMetadata:
    pmid: PMID
    csl_data: dict = field(default_factory=dict)
    error: str | None = None
    status_code: int = 200

    @property
    def is_valid(self) -> bool:
        return self.error is None and bool(self.csl_data)

    def to_csl_json(self) -> dict[str, Any]:
        if self.csl_data:
            csl = self.csl_data.copy()
            csl["id"] = self.pmid
            return csl
        return {
            "id": self.pmid,
            "type": "article-journal",
            "title": f"[Error] {self.error or 'Fetch failed'}",
            "author": [{"family": f"PMID: {self.pmid}", "given": ""}],
            "issued": {"date-parts": [[0]]}
        }

class PubMedClient:
    def __init__(self, settings: Settings, override_key: str | None = None):
        self.settings = settings
        api_key = override_key or settings.api_key
        if api_key:
            self.rate, self.workers = 9.0, 10
            self.api_key = api_key
        else:
            self.rate, self.workers = 3.0, 3
            self.api_key = None
            print("Note: API key not set. Running in slow mode (3 calls/sec).")

        self.lock = threading.Lock()
        self.next_call = 0.0

        self.session = requests.Session()
        retry = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def _wait_rate_limit(self):
        with self.lock:
            now = time.time()
            wait_time = max(0.0, self.next_call - now)
            self.next_call = now + wait_time + (1.0 / self.rate)
        if wait_time > 0:
            time.sleep(wait_time)

    def _fetch_single(self, pmid: PMID) -> ArticleMetadata:
        self._wait_rate_limit()
        params = {"format": "csl", "id": pmid}
        if self.api_key:
            params["api_key"] = self.api_key
        try:
            resp = self.session.get(self.settings.api_base_url, params=params, timeout=self.settings.api_timeout)
            if resp.status_code == 404:
                return ArticleMetadata(pmid=pmid, error="Not found", status_code=404)
            resp.raise_for_status()
            return ArticleMetadata(pmid=pmid, csl_data=resp.json())
        except Exception as e:
            return ArticleMetadata(pmid=pmid, error=str(e), status_code=500)

    def fetch_all(self, pmids: list[PMID]) -> dict[PMID, ArticleMetadata]:
        if not pmids: return {}
        print(f"Fetching {len(pmids)} articles from PubMed (Workers: {self.workers})...")
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as executor:
            for future in concurrent.futures.as_completed({executor.submit(self._fetch_single, p): p for p in pmids}):
                meta = future.result()
                results[meta.pmid] = meta
        return results

def download_csl_style(style_name: str, repo_url: str) -> bool:
    """GitHubからCSLファイルをダウンロードする"""
    if style_name.startswith(("http://", "https://")):
        return True  # 既にURL指定されているためダウンロード不要

    if not style_name.endswith(".csl"):
        style_name += ".csl"

    dest_path = Path(style_name)
    if dest_path.exists():
        return True

    print(f"Attempting to download CSL style: {style_name}...")
    try:
        r = requests.get(repo_url + style_name, timeout=10)
        if r.status_code == 200:
            dest_path.write_text(r.text, encoding="utf-8")
            print(f"✓ Downloaded CSL style: {style_name}")
            return True
        else:
            print(f"  - Failed to download {style_name} (Status: {r.status_code})")
    except Exception as e:
        print(f"  - Error downloading CSL: {e}")
    return False

def get_yaml_data(text: str) -> tuple[Any, str]:
    """YAMLブロックを解析して、(データ, YAML原文) を返す"""
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

def normalize_markdown(text: str) -> tuple[str, set[PMID]]:
    """連続するQuartoタグを結合し、全PMIDを抽出する。"""
    def merge_tags(match):
        pmids = RE_PMID_EXTRACT.findall(match.group(0))
        seen = set()
        unique_pmids = [p for p in pmids if not (p in seen or seen.add(p))]
        return f"[@{'; @'.join(unique_pmids)}]"
    text = RE_CONSECUTIVE.sub(merge_tags, text)

    pmids = set(RE_PMID_EXTRACT.findall(text))
    return text, pmids

def update_yaml_frontmatter(yaml_raw: str, body_text: str, bib_filename: str, yaml_data: dict) -> str:
    """yaml_data に bibliography を追記し、更新があれば新YAMLを、なければ元のテキストを返す"""
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
    """カレントディレクトリから対象ファイルを検索し、CUIメニューまたはGUIで選択させる"""
    cands = list(Path.cwd().glob("*.qmd")) + list(Path.cwd().glob("*.md"))

    if not cands:
        print("Error: No .qmd or .md files found in the current directory.")
        return None

    if len(cands) == 1:
        print(f"Auto-selected: {cands[0].name}")
        return cands[0]

    if sys.stdin and sys.stdin.isatty():
        print("\nSelect Target Document:")
        for i, f in enumerate(cands, 1):
            print(f"  {i}. {f.name}")
        print("  0. Open File Dialog (GUI)")

        while True:
            try:
                c = input("Select (number): ").strip()
                if c == '0':
                    break  # TkinterのGUIへフォールバック
                elif c.isdigit() and 1 <= int(c) <= len(cands):
                    return cands[int(c)-1]
                else:
                    print("Invalid input. Please enter a valid number.")
            except (EOFError, KeyboardInterrupt):
                print("\nCancelled.")
                return None

    # TTY環境でない、または '0' が選択された場合はTkinterを起動
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askopenfilename(
            title="Select Document",
            filetypes=[("Quarto/Markdown", "*.qmd *.md"), ("All", "*.*")]
        )
        root.destroy()
        return Path(path) if path else None
    except Exception as e:
        print(f"GUI dialog failed ({e}).")
        return None

def main() -> int:
    settings = Settings()

    parser = argparse.ArgumentParser(description=f"QuartoPmid v{__version__} - Quarto PubMed Sync Tool")
    parser.add_argument("input_file", nargs="?", help="Input .qmd or .md file. Leave empty for menu.")
    # Settingsクラスのデフォルト値と連動するCLIオプション
    parser.add_argument("--update-yaml", action=argparse.BooleanOptionalAction, default=settings.update_yaml,
                        help="Auto-inject bibliography into YAML frontmatter")
    parser.add_argument("--download-csl", action=argparse.BooleanOptionalAction, default=settings.download_csl,
                        help="Auto-download CSL style defined in YAML")
    parser.add_argument("--api-key", help="NCBI API Key (overrides environment variable)")
    args = parser.parse_args()

    # ファイルの決定 (引数がなければメニュー起動)
    in_path = Path(args.input_file) if args.input_file else _select_target_file()

    if not in_path or not in_path.exists():
        if args.input_file:
            print(f"Error: File '{in_path}' not found.")
        return 1

    original_text = in_path.read_text(encoding="utf-8")
    bib_path = in_path.with_suffix(".json")
    bib_filename = bib_path.name

    # 1. テキスト正規化とPMID抽出（文字数変動を確定させるため最初に実行）
    processed_text, pmids = normalize_markdown(original_text)

    # 2. YAML解析とCSL自動ダウンロード
    yaml_data, yaml_raw = get_yaml_data(processed_text)
    if yaml_data and args.download_csl:
        csl_value = yaml_data.get("csl")
        if isinstance(csl_value, str):
            download_csl_style(csl_value, settings.csl_repo_url)

    # 3. YAML連携 (bibliography追記)
    if args.update_yaml:
        if yaml_data is not None:
            body = processed_text[len(yaml_raw):]
            processed_text = update_yaml_frontmatter(yaml_raw, body, bib_filename, yaml_data)
        elif not yaml_raw:
            processed_text = f"---\nbibliography: {bib_filename}\n---\n\n{processed_text}"
        else:
            print("Warning: YAML parsing failed. Skipping YAML update.")

    # 4. 文献データの同期
    existing_bib = {}
    if bib_path.exists():
        try:
            with open(bib_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                existing_bib = {str(item.get("id")): item for item in data if "id" in item}
        except Exception: pass

    missing_pmids = [p for p in pmids if p not in existing_bib or existing_bib[p].get("title", "").startswith("[Error]")]

    if missing_pmids:
        client = PubMedClient(settings, override_key=args.api_key)
        new_meta = client.fetch_all(missing_pmids)
        updated_count = 0
        for p, meta in new_meta.items():
            if meta.is_valid or meta.status_code == 404:
                existing_bib[p] = meta.to_csl_json()
                updated_count += 1
            else:
                print(f"  - PMID {p}: Fetch failed ({meta.error})")

        if updated_count > 0:
            export_list = sorted(existing_bib.values(), key=lambda x: str(x.get("id", "")))
            with open(bib_path, "w", encoding="utf-8") as f:
                json.dump(export_list, f, ensure_ascii=False, indent=2)
            print(f"✓ Bibliography synced: {bib_filename} (Total: {len(export_list)})")
        else:
            print("Warning: All fetches failed. Bibliography not updated.")
    else:
        if pmids: print("✓ All PMIDs are already cached in bibliography.")

    # 5. 原稿の書き出し（冪等性の確保）
    if processed_text == original_text:
        print("✓ No changes needed in the document.")
        return 0

    bak_path = in_path.with_suffix(in_path.suffix + ".bak")
    if not bak_path.exists() or bak_path.read_text(encoding="utf-8") != original_text:
        shutil.copy2(in_path, bak_path)
        print(f"✓ Backup created: {bak_path.name}")

    in_path.write_text(processed_text, encoding="utf-8")
    print(f"✓ Overwrote original file: {in_path.name}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
