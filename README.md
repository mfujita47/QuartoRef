# 📘 QuartoPmid (v1.1.0)

[English](#english) | [日本語](#日本語)

---

## English

**QuartoPmid** is a lightweight CLI tool designed for [Quarto](https://quarto.org/) users. It automatically organizes [PubMed](https://pubmed.ncbi.nlm.nih.gov/) IDs (PMIDs) in your manuscripts (`.qmd` or `.md`), fetches the latest bibliographic metadata via the [PubMed API](https://www.ncbi.nlm.nih.gov/home/develop/api/), and generates [CSL-JSON](https://citeproc-js.readthedocs.io/en/latest/csl-json/markup.html) files.

By restricting citations to [PubMed](https://pubmed.ncbi.nlm.nih.gov/) and using PMIDs directly as citation keys, it completely eliminates the need for maintaining a local bibliography database. Since the master data is centralized online, it also prevents citation inconsistencies during collaboration. The `.qmd` / `.md` workflow maintains high affinity with LLMs (Generative AI) while simplifying the synchronization of the latest bibliographic metadata—a process that was previously a bottleneck in research automation.

While sharing the same core philosophy as its predecessor, [PyRefPmid](https://github.com/mfujita47/PyRefPmid), this tool has been streamlined by decoupling rendering and file conversion features. By specializing exclusively in "**Automating PubMed citation synchronization and management**," it provides a significantly simpler and faster experience.

### ✨ Key Features

- **Automatic Citation Normalization**: Detects [Quarto-standard](https://quarto.org/docs/authoring/footnotes-and-citations.html) `[@PMID]` tags and intelligently merges consecutive tags (e.g., `[@123] [@456]` becomes `[@123; @456]`).
- **PubMed Data Sync**: Fetches metadata from the [PubMed API](https://www.ncbi.nlm.nih.gov/home/develop/api/) and saves it in the [CSL-JSON](https://citeproc-js.readthedocs.io/en/latest/csl-json/markup.html) format required by [Quarto](https://quarto.org/).
- **Automatic YAML Update**: Automatically manages the `bibliography` field in your [YAML](https://yaml.org/) front matter without breaking existing comments or formatting.
- **Standalone & Portable**: Operates as a single-file script. No complex setup or package installation required—just copy `QuartoPmid.py` to your project.
- **Automatic Setup**: Automatically downloads [CSL](https://citationstyles.org/) styles, implements high-speed caching, and creates backups before execution.

### 📦 Installation

The tool is a single Python script. Requires [Python](https://www.python.org/) 3.9 or higher. **Please install the necessary libraries ([requests](https://pypi.org/project/requests/) and [ruamel.yaml](https://pypi.org/project/ruamel.yaml/)) before use:**

```bash
pip install requests ruamel.yaml
```

### 🚀 Usage

No options required by default. Just run the script to select a file:

```bash
python QuartoPmid.py
```

#### Test Run

You can quickly test the tool using the included [test_draft.md](./test_draft.md):

```bash
# Run against the test file
python QuartoPmid.py test_draft.md
```

After execution, verify that `test_draft.json` is generated and the tags in `test_draft.md` are organized.

#### PMID Syntax

Use the `[@PMID]` format for [PubMed](https://pubmed.ncbi.nlm.nih.gov/) IDs:

- Single citation: `[@12345678]`
- Multiple citations: `[@12345678; @87654321]` or `[@12345678] [@87654321]` (the latter is automatically merged)

### CLI Options

| Option              | Description                                                                       | Default          |
| :------------------ | :-------------------------------------------------------------------------------- | :--------------- |
| `input_file`        | Target `.qmd` or `.md` file.                                                      | (Menu selection) |
| `--update-yaml`     | Auto-register the generated [JSON](https://www.json.org/) in YAML `bibliography`. | **ON**           |
| `--no-update-yaml`  | Disable automatic YAML update.                                                    | -                |
| `--download-csl`    | Auto-download [CSL](https://citationstyles.org/) styles listed in YAML.           | **ON**           |
| `--no-download-csl` | Disable automatic CSL download.                                                   | -                |
| `--api-key KEY`     | Specify your [NCBI API Key](https://www.ncbi.nlm.nih.gov/account/settings/).      | (Env variable)   |

### 🛠 Rendering with Quarto

Once `QuartoPmid` has organized your citations and generated the [CSL-JSON](https://citeproc-js.readthedocs.io/en/latest/csl-json/markup.html) file, render your document using the standard [Quarto](https://quarto.org/) workflow:

- **Command Line**:
  ```bash
  quarto render your_file.qmd --to pdf
  ```
- **VS Code**: Use the [Quarto Extension](https://marketplace.visualstudio.com/items?itemName=quarto.quarto) and click the **Render** button or press `Ctrl+Shift+K`.

### ⚙️ Settings & Customization

#### 1. API Key Setup

Setting an [NCBI API Key](https://www.ncbi.nlm.nih.gov/account/settings/) significantly increases processing speed (from 3 to 9 requests per second). You can set it in three ways:

- **Environment Variable**: Set `NCBI_API_KEY` (Recommended).
- **CLI Option**: Use `--api-key YOUR_KEY`.
- **Script Edit**: Modify the `api_key` field in the `Settings` class directly (see below).

#### 2. Default Behavior

You can permanently change default behaviors by editing the `Settings` dataclass at the top of the script.

```python
@dataclass(frozen=True)
class Settings:
    update_yaml: bool = True   # Always update YAML
    download_csl: bool = True  # Always download CSL
    api_key: str = "your_api_key_here"
```

---

## 日本語

**QuartoPmid** は、[Quarto](https://quarto.org/) (`.qmd`) や [Markdown](https://daringfireball.net/projects/markdown/) (`.md`) 原稿内の [PubMed](https://pubmed.ncbi.nlm.nih.gov/) ID (PMID) を自動整理し、[PubMed API](https://www.ncbi.nlm.nih.gov/home/develop/api/) から最新の書誌情報を取得して [CSL-JSON](https://citeproc-js.readthedocs.io/en/latest/csl-json/markup.html) を生成する、[Quarto](https://quarto.org/) ユーザーに特化した軽量な CLI ツールです。

引用文献を [PubMed](https://pubmed.ncbi.nlm.nih.gov/) 掲載論文に限定し、PubMed ID (PMID) をそのまま引用キーとして扱うことで、煩雑な文献データベース構築の手間を完全に排除しました。マスターデータがオンラインに集約されているため、共同執筆時における「文献情報の不整合」という課題も発生しません。`.qmd` や `.md` 形式の採用により LLM (生成AI) との親和性を維持しつつ、これまで自動化のボトルネックであった「最新の書誌情報同期」を極めてシンプルに解決します。

前身の [PyRefPmid](https://github.com/mfujita47/PyRefPmid) と基本理念を共有しつつ、レンダリングやファイル変換などの機能を大胆に削ぎ落とし、「**PubMed 掲載論文の同期と管理の自動化**」という一点に特化したことで、圧倒的にシンプルで高速な動作を実現しました。

### ✨ 主な機能

- **引用タグの自動正規化**: [Quarto 標準記法](https://quarto.org/docs/authoring/footnotes-and-citations.html)である `[@PMID]` 引用タグを検出し、連続するタグを `[@12345678; @87654321]` 形式へスマートに統合します。
- **PubMed データの自動同期**: [PubMed API](https://www.ncbi.nlm.nih.gov/home/develop/api/) から最新の書誌情報を取得し、[Quarto](https://quarto.org/) 標準の [CSL-JSON](https://citeproc-js.readthedocs.io/en/latest/csl-json/markup.html) 形式で保存します。
- **YAML フロントマターの自動更新**: 原稿内の `bibliography` 設定（[YAML](https://yaml.org/)）をツールが自動で管理。既存のコメントや書式を壊さずに更新します。
- **スタンドアロン・ポータブル**: 単一のスクリプトファイルとして動作します。複雑な導入作業は不要で、`QuartoPmid.py` をプロジェクトにコピーするだけで利用可能です。
- **不足ファイルの自動セットアップ**: [CSL](https://citationstyles.org/) スタイルの自動取得、キャッシュ機能、実行前の自動バックアップなど、面倒な準備をすべて自動化します。

### 📦 インストール

本ツールは単一の Python スクリプトとして提供されます。[Python](https://www.python.org/) 3.9 以上が必要です。**実行には外部ライブラリ（[requests](https://pypi.org/project/requests/) および [ruamel.yaml](https://pypi.org/project/ruamel.yaml/)）が必要ですので、事前にインストールしてください。**

```bash
pip install requests ruamel.yaml
```

### 🚀 使い方

オプション指定なしで利用可能です。実行するとファイル選択メニューが表示されます：

```bash
python QuartoPmid.py
```

#### テスト実行

同梱されている [test_draft.md](./test_draft.md) を使用して、動作をすぐに試すことができます。

```bash
python QuartoPmid.py test_draft.md
```

#### PMID 記法

原稿内では `[@PMID]` という形式で [PubMed](https://pubmed.ncbi.nlm.nih.gov/) ID を記述します。

- 単一の引用: `[@12345678]`
- 複数の引用: `[@12345678; @87654321]` または `[@12345678] [@87654321]` （後者は実行後に自動統合されます）

### コマンドラインオプション

| オプション          | 説明                                                                                | デフォルト       |
| :------------------ | :---------------------------------------------------------------------------------- | :--------------- |
| `input_file`        | 対象の原稿ファイル (`.qmd` / `.md`) を指定します。                                  | (メニュー選択)   |
| `--update-yaml`     | 生成した [JSON](https://www.json.org/) を YAML の `bibliography` に自動登録します。 | **ON**           |
| `--no-update-yaml`  | YAML の自動更新を無効にします。                                                     | -                |
| `--download-csl`    | YAML に記載された [CSL](https://citationstyles.org/) スタイルを自動取得します。     | **ON**           |
| `--no-download-csl` | CSL の自動取得を無効にします。                                                      | -                |
| `--api-key KEY`     | [NCBI API キー](https://www.ncbi.nlm.nih.gov/account/settings/)を直接指定します。   | (環境変数を使用) |

### 🛠 Quarto でのレンダリング

`QuartoPmid` で引用タグの整理と書誌情報の取得が完了したら、通常の [Quarto](https://quarto.org/) ワークフローでレンダリングを行ってください。

- **コマンドライン**:
  ```bash
  quarto render your_file.qmd --to pdf
  ```
- **VS Code**: [Quarto 拡張機能](https://marketplace.visualstudio.com/items?itemName=quarto.quarto)をインストールし、**Render** ボタンをクリックするか `Ctrl+Shift+K` を入力します。

### ⚙️ 設定とカスタマイズ

#### 1. API キーの設定

大量の文献を一括処理する場合は、[NCBI API キー](https://www.ncbi.nlm.nih.gov/account/settings/)を設定することで、処理速度が大幅に向上します（3回/秒 → 9回/秒）。

- **環境変数**: `NCBI_API_KEY` にキーを設定（推奨）。
- **CLI オプション**: 実行時に `--api-key YOUR_KEY` を付与。
- **スクリプト編集**: `Settings` クラスの `api_key` を直接書き換え (下記参照)。

#### 2. デフォルト挙動の変更

スクリプト上部の `Settings` データクラスを書き換えることで、デフォルトの挙動を固定できます。

```python
@dataclass(frozen=True)
class Settings:
    update_yaml: bool = True
    download_csl: bool = True
    api_key: str = "your_api_key_here"
```

---

## 🧑‍💻 Author / License

- **Author**: [mfujita47](https://github.com/mfujita47) (Mitsugu Fujita)
- **License**: [MIT License](https://opensource.org/licenses/MIT)
