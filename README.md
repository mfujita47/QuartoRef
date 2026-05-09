# 📘 QuartoPmid (v1.0.0)

**QuartoPmid** は、Quarto (`.qmd`) や Markdown 原稿内の PubMed ID (PMID) を自動整理し、PubMed API から最新の書誌情報を取得して CSL-JSON を生成する、Quarto ユーザーに特化した軽量な CLI ツールです。

旧 `PyRefPmid` からレンダリングやファイル変換の機能を切り離し、「**Quarto のネイティブな引用システムへの橋渡し**」に完全に特化させたことで、より堅牢で高速な動作を実現しました。

---

## ✨ 主な機能

- **Quarto 標準記法への完全対応**: `[@123456]` 形式の引用タグを検出。
- **スマート・タグ統合**: 連続する引用タグ `[@123] [@456]` を、見やすく `[@123; @456]` に自動結合。
- **YAML フロントマターの安全な同期**: 
  - 生成された JSON ファイルを YAML の `bibliography` フィールドに自動追記。
  - `ruamel.yaml` を採用し、YAML 内の既存のコメントやフォーマットを一切壊さずに更新します。
- **CSL スタイルの自動取得**: 
  - YAML に記載された `csl: nature.csl` などの指定を読み取り、ローカルにファイルがなければ公式リポジトリから自動ダウンロードします。
- **冪等性（べきとうせい）の確保**: 
  - API 通信のローカルキャッシュと、原稿に変更がない場合の書き込みスキップ機能により、何度実行しても安全かつ瞬時に終了します。
- **安全な自動バックアップ**: 原稿を直接上書き更新する仕様ですが、実行前には常に `.bak` バックアップが作成されるため安全です。

---

## 📦 インストール

Python 3.9 以上が必要です。以下のライブラリをインストールしてください。

```bash
pip install requests ruamel.yaml

```

> **🔑 APIキーの設定 (推奨):**
> 大量の文献を一括処理する場合は、環境変数 `NCBI_API_KEY` に PubMed の API キーを設定しておくと、制限が緩和され（3回/秒 → 9回/秒）高速に動作します。

---

## 🚀 使い方

基本の実行（カレントディレクトリに複数のファイルがある場合はメニューが表示されます）：

```bash
python QuartoPmid.py

```

### 実践的なオプション

**1. YAML 連携と自動更新 (`--update-yaml`)**
原稿を直接更新（常に自動バックアップ作成）し、同時に YAML へ文献リストを自動登録します。

```bash
python QuartoPmid.py draft.qmd --update-yaml

```

**2. CSL スタイルの自動準備 (`--download-csl`)**
YAML に書かれたスタイルファイルを自動的に GitHub から取得します。

```bash
python QuartoPmid.py draft.qmd --download-csl

```

**3. 全自動ワークフロー (おすすめ)**

```bash
python QuartoPmid.py draft.qmd --update-yaml --download-csl

```

---

## 🛠️ カスタマイズ (Settings クラス)

スクリプト上部の `Settings` データクラスを書き換えることで、自分の執筆スタイルに合わせてデフォルトの挙動（常に上書きする、常に YAML を更新するなど）を固定できます。

```python
@dataclass(frozen=True)
class Settings:
    update_yaml: bool = True   # 常にYAML更新をONにする
    download_csl: bool = True  # 常にCSLダウンロードをONにする

```

---

## 💡 Quarto でのレンダリング

QuartoPmid で準備が整った後は、通常の Quarto コマンドで PDF や HTML を生成するだけです。

```bash
# 例: PDFへのレンダリング
quarto render draft.qmd --to pdf

```

---

## 🧑‍💻 作者 / ライセンス

* **Author**: mfujita47 (Mitsugu Fujita)
* **License**: [MIT License](https://www.google.com/search?q=LICENSE)
