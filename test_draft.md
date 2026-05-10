---
title: "QuartoRef 動作検証用テスト原稿"
author: "Test User"
date: "2026-05-10"
format:
  html:
    toc: true
    number-sections: true
csl: elsevier-vancouver.csl
---

# QuartoRef テスト用ファイル

このファイルは `QuartoRef.py` の動作をテストするために使用されます。
引用タグには `pmid:` または `doi:` のプレフィックスが必要です。

## 1. 基本的な引用のテスト

PMID の引用: [@pmid:10000001]
DOI の引用: [@doi:10.1038/nature12345]

存在しない ID（エラーハンドリングのテスト）: [@pmid:99999999] [@doi:10.fake.id/nonexistent]

## 2. 連続タグのスマート結合テスト

連続するタグは自動的に統合されます。

PMID と DOI の混在: [@pmid:10000002] [@doi:10.1000/1]
スペースや改行を含む場合:
[@pmid:10000003]
[@pmid:10000004]

## 3. 正規化のテスト

大文字 DOI の小文字化: [@doi:10.1038/NATURE12345]
末尾の句読点除去: [@doi:10.1038/nature12345.] と [@doi:10.1038/nature12345],

## 4. セミコロンを含む DOI

セミコロンを含む DOI は `%3B` にエンコードして記述します。
[@doi:10.1101/2021.01.01.424982%3Bv1]

## 5. 無視される形式

プレフィックスのない旧形式は無視されます: [@10000005]

## References

（※Quartoでのレンダリング時、ここに自動的に文献リストが出力されます）
