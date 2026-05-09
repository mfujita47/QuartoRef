# 📘 QuartoPmid (v1.1.0)

**QuartoPmid** は、[Quarto](https://quarto.org/) (`.qmd`) や [Markdown](https://daringfireball.net/projects/markdown/) (`.md`) 原稿内の [PubMed](https://pubmed.ncbi.nlm.nih.gov/) ID (PMID) を自動整理し、[PubMed API](https://www.ncbi.nlm.nih.gov/home/develop/api/) から最新の書誌情報を取得して [CSL](https://citationstyles.org/)-[JSON](https://www.json.org/) を生成する、[Quarto](https://quarto.org/) ユーザーに特化した軽量な CLI ツールです。

旧 [PyRefPmid](https://github.com/mfujita47/PyRefPmid) からレンダリングやファイル変換の機能を切り離し、「**[PubMed](https://pubmed.ncbi.nlm.nih.gov/)  文献の取得と管理の自動化**」に機能を絞り込んだことで、よりシンプルで迷いのない操作感と高速な動作を実現しました。

## ✨ 主な機能

- **引用タグの自動正規化**: [Quarto 標準記法](https://quarto.org/docs/authoring/footnotes-and-citations.html)である `[@PMID]` を検出し、連続するタグを `[@12345678; @87654321]` 形式へスマートに統合します。
- **[PubMed](https://pubmed.ncbi.nlm.nih.gov/) データの自動同期**: [PubMed API](https://www.ncbi.nlm.nih.gov/home/develop/api/) から最新の書誌情報を取得し、[Quarto](https://quarto.org/) 標準の [CSL](https://citationstyles.org/)-[JSON](https://www.json.org/) 形式で保存します。
- **[YAML](https://yaml.org/) 設定のスマートな自動更新**: 原稿内の `bibliography` 設定をツールが自動で管理。既存のコメントや書式を壊さずに更新します。
- **不足ファイルの自動セットアップ**: [CSL](https://citationstyles.org/) スタイルの自動取得、高速なキャッシュ、実行前の自動バックアップなど、面倒な準備をすべて自動化します。

## 📦 インストール

[Python](https://www.python.org/) 3.9 以上が必要です。以下のライブラリをインストールしてください。

```bash
pip install requests ruamel.yaml
```


## 🚀 使い方

基本の実行（引数なしで実行すると、カレントディレクトリのファイルをリストアップし、メニューから選択できます）：

```bash
python QuartoPmid.py
```

### テスト実行

同梱されている [test_draft.md](./test_draft.md) を使用して、動作をすぐに試すことができます。

```bash
# テストファイルに対して実行
python QuartoPmid.py test_draft.md
```

実行後、`test_draft.json` が生成され、`test_draft.md` 内のタグが整理されていることを確認してください。

### 指定方法と PMID 記法

原稿内では `[@PMID]` という形式で [PubMed](https://pubmed.ncbi.nlm.nih.gov/) ID を記述します。

- 単一の引用: `[@12345678]`
- 複数の引用: `[@12345678] [@87654321]` （実行後に `[@12345678; @87654321]` へ自動統合されます）

### 実践的なオプション

| オプション          | 説明                                                       | デフォルト       |
| :------------------ | :--------------------------------------------------------- | :--------------- |
| `input_file`        | 対象の `.qmd` または `.md` ファイルを指定します。          | (メニュー選択)   |
| `--update-yaml`     | 生成した [JSON](https://www.json.org/) を [YAML](https://yaml.org/) の `bibliography` に自動登録します。 | **ON**           |
| `--no-update-yaml`  | [YAML](https://yaml.org/) の自動更新を無効にします。                            | -                |
| `--download-csl`    | YAML に記載された [CSL](https://citationstyles.org/) スタイルを自動取得します。           | **ON**           |
| `--no-download-csl` | [CSL](https://citationstyles.org/) の自動取得を無効にします。                             | -                |
| `--api-key KEY`     | [NCBI API キー](https://www.ncbi.nlm.nih.gov/account/settings/)を直接指定します。                            | (環境変数を使用) |

**例: 特定のファイルに対し、[YAML](https://yaml.org/) 更新なしで実行する場合**

```bash
python QuartoPmid.py draft.qmd --no-update-yaml
```

## ⚙️ 設定とカスタマイズ

### 1. API キーの設定

大量の文献を一括処理する場合は、[PubMed](https://pubmed.ncbi.nlm.nih.gov/) の [API キー](https://www.ncbi.nlm.nih.gov/account/settings/)を設定することで、処理速度が大幅に向上します（3回/秒 → 9回/秒）。設定方法は以下の 3 通りです。

| 方法 | 手順 |
| :--- | :--- |
| **環境変数** | `NCBI_API_KEY` にキーを設定（推奨）。 |
| **CLI オプション** | 実行時に `--api-key YOUR_KEY` を付与。 |
| **スクリプト編集** | 下記の `Settings` クラスの `api_key` を直接書き換え。 |

### 2. デフォルト挙動の変更 (Settings クラス)

スクリプト上部の `Settings` データクラスを書き換えることで、自分の執筆スタイルに合わせてデフォルトの挙動を固定できます。

```python
@dataclass(frozen=True)
class Settings:
    update_yaml: bool = True   # 常にYAML更新をONにする
    download_csl: bool = True  # 常にCSLダウンロードをONにする
    api_key: str = "your_api_key_here"  # APIキーを直接記載する場合
```

## 💡 Quarto でのレンダリング

[QuartoPmid](https://github.com/mfujita47/QuartoPmid) で準備が整った後は、通常の [Quarto](https://quarto.org/) コマンド、あるいは [VSCode](https://code.visualstudio.com/) の [Quarto 拡張機能](https://marketplace.visualstudio.com/items?itemName=quarto.quarto)（Render ボタンやショートカット）で PDF や HTML を生成するだけです。

```bash
# 例: CLIでのPDFレンダリング
quarto render draft.qmd --to pdf
```

## 🧑‍💻 作者 / ライセンス

- **Author**: [mfujita47](https://github.com/mfujita47) (Mitsugu Fujita)
- **License**: [MIT License](https://opensource.org/licenses/MIT)
