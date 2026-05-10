# 📘 QuartoRef (v1.2.0)

[English](#english) | [日本語](#日本語)

---

## English

**QuartoRef** is a lightweight CLI tool designed for [Quarto](https://quarto.org/) users. It automatically organizes citations in your manuscripts (`.qmd` or `.md`), fetches the latest bibliographic metadata from [PubMed](https://pubmed.ncbi.nlm.nih.gov/) and [DOI](https://doi.org/) (via Crossref), and generates [CSL-JSON](https://citeproc-js.readthedocs.io/en/latest/csl-json/markup.html) files.

By using PMIDs and DOIs directly as citation keys, it completely eliminates the need for maintaining a local bibliography database. Since the master data is centralized online, it also prevents citation inconsistencies during collaboration. The `.qmd` / `.md` workflow maintains high affinity with LLMs (Generative AI) while simplifying the synchronization of the latest bibliographic metadata—a process that was previously a bottleneck in research automation.

### ✨ Key Features

- **No Manual Database Maintenance**: Use `[@pmid:ID]` or `[@doi:ID]` directly in your text. The tool fetches everything for you.
- **Smart Citation Cleaning**: Automatically merges consecutive tags (e.g., `[@pmid:1] [@pmid:2]` becomes `[@pmid:1; @pmid:2]`) and fixes accidental trailing punctuation or case issues.
- **Zero-Configuration YAML Management**: The tool automatically registers the generated bibliography file in your YAML front matter.
- **Fail-Safe Processing**: Even if a network error occurs or an ID is invalid, the tool generates a "placeholder" to ensure your Quarto document still renders without errors.
- **Portable & Standalone**: It's just a single Python file. Copy it to your project folder and you're ready to go.

### 📦 Installation

Requires [Python](https://www.python.org/) 3.9 or higher. **Please install the necessary libraries before use:**

```bash
pip install requests ruamel.yaml python-dotenv
```

### 🚀 Usage

No options required by default. Just run the script to select a file:

```bash
python QuartoRef.py
```

#### Citation Syntax

Citations must include the `pmid:` or `doi:` prefix:

- **PubMed**: `[@pmid:12345678]`
- **DOI**: `[@doi:10.1038/nature12345]`
- **Multiple**: `[@pmid:123; @doi:10.1038/nature12345]`

> **Note**: If a DOI contains a semicolon (`;`), you **must** manually write it as `%3B` in your manuscript (e.g., `[@doi:10.1101/abc%3Bv1]`). This prevents Quarto from misidentifying the semicolon as a citation separator.


### CLI Options

| Option          | Description                                                                       | Default          |
| :-------------- | :-------------------------------------------------------------------------------- | :--------------- |
| `input_file`    | Target `.qmd` or `.md` file.                                                      | (Menu selection) |
| `--email EMAIL` | Set your email to get better API limits for DOI fetching.                         | (Env `EMAIL`)    |
| `--api-key KEY` | Set your [NCBI API Key](https://www.ncbi.nlm.nih.gov/account/settings/) for speed. | (Env `NCBI_API_KEY`) |

### 🛠 Rendering with Quarto

Once `QuartoRef` has organized your citations, render your document normally:

- **Command Line**: `quarto render your_file.qmd`
- **VS Code**: Click the **Render** button in the Quarto extension.

---

## 日本語

**QuartoRef** は、[Quarto](https://quarto.org/) (`.qmd`) や [Markdown](https://daringfireball.net/projects/markdown/) (`.md`) 原稿内の引用タグを自動整理し、[PubMed](https://pubmed.ncbi.nlm.nih.gov/) および [DOI](https://doi.org/) (Crossref) から最新の書誌情報を取得して [CSL-JSON](https://citeproc-js.readthedocs.io/en/latest/csl-json/markup.html) を生成する、軽量な CLI ツールです。

PMID や DOI をそのまま引用キーとして扱うことで、煩雑な文献データベース構築の手間を完全に排除しました。マスターデータがオンラインに集約されているため、共同執筆時における情報の不整合も発生しません。LLM（生成AI）との親和性を維持しつつ、これまで自動化のボトルネックであった「最新の書誌情報同期」を極めてシンプルに解決します。

### ✨ 主な特長

- **文献リストの管理が不要に**: 本文中に `[@pmid:ID]` や `[@doi:ID]` と書くだけで、ツールが自動で情報を集めてきます。
- **引用タグを自動で「お掃除」**: 連続するタグの統合（`[@pmid:1] [@pmid:2]` → `[@pmid:1; @pmid:2]`）や、大文字小文字の乱れ、末尾の不要な句読点などを自動で修正します。
- **YAML 設定もおまかせ**: 生成された文献ファイルを YAML フロントマターの `bibliography` に自動で登録。設定の手間を省きます。
- **エラーに強い設計**: 万が一ネットワークエラーや ID の間違いがあっても、仮のデータを生成して Quarto のレンダリング（PDF/HTML作成）が止まらないように配慮します。
- **どこでも動くポータブル設計**: スクリプト 1 ファイルだけで動作。プロジェクトフォルダにコピーするだけで準備完了です。

### 📦 インストール

[Python](https://www.python.org/) 3.9 以上が必要です。**実行前に必要なライブラリをインストールしてください：**

```bash
pip install requests ruamel.yaml python-dotenv
```

### 🚀 使い方

オプションなしで実行すると、ファイル選択メニューが表示されます：

```bash
python QuartoRef.py
```

#### 引用の書き方

引用タグには `pmid:` または `doi:` のプレフィックスが必要です：

- **PubMed**: `[@pmid:12345678]`
- **DOI**: `[@doi:10.1038/nature12345]`
- **複数引用**: `[@pmid:123; @doi:10.1038/nature12345]`

> **注意**: DOIの中にセミコロン（`;`）が含まれる場合は、原稿内では**手動で** `%3B` に書き換えて記述してください（例: `[@doi:10.1101/abc%3Bv1]`）。これは、Quartoがセミコロンを「文献の区切り文字」と誤認してビルドエラーになるのを防ぐためです。

### コマンドラインオプション

| オプション      | 説明                                                                                | デフォルト       |
| :-------------- | :---------------------------------------------------------------------------------- | :--------------- |
| `input_file`    | 対象の原稿ファイル (`.qmd` / `.md`)。                                               | (メニュー選択)   |
| `--email EMAIL` | DOI 取得時の制限を緩和するためのメールアドレス。                                     | (環境変数 `EMAIL`) |
| `--api-key KEY` | PubMed の取得を高速化する [API キー](https://www.ncbi.nlm.nih.gov/account/settings/)。 | (環境変数 `NCBI_API_KEY`) |

### 🛠 Quarto でのレンダリング

`QuartoRef` での整理が終わったら、通常通り Quarto で出力してください：

- **コマンドライン**: `quarto render your_file.qmd`
- **VS Code**: Quarto 拡張機能の **Render** ボタンをクリック。

---

## 🧑‍💻 Author / License

- **Author**: [mfujita47](https://github.com/mfujita47) (Mitsugu Fujita)
- **License**: [MIT License](https://opensource.org/licenses/MIT)
