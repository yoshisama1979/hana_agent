# CLAUDE.md

## プロジェクト概要

- 仕様書: `documents/document.md`
- テスト仕様書: `documents/test.csv`
- プロジェクト固有の定義（スタック・アカウント種別・ディレクトリ等）: `project-config.md`

## 環境

プロジェクトルートやコマンド実行方法は `project-config.md` を参照すること。

## ルールファイル (rules/)

| ファイル | いつ参照するか |
|---------|--------------|
| `agent.md` | 常に（実装フロー・共通原則） |
| `dev.md` | 実装時（開発規約） |
| `tdd.md` | テスト作成時（BDDシナリオ・RGBCサイクル・三者整合性チェック） |
| `testcode.md` | バックエンドテスト作成時 |
| `frontend-test.md` | フロントエンドテスト作成時 |
| `create_test.md` | テスト仕様書（CSV）作成時 |
| `refactoring.md` | リファクタリング時 |
| `coding.md` | コーディング時（CSS/Sass・HTML・PHP定数の規約） |
| `setup.md` | 初回セットアップ時のみ（SCSS自動コンパイル等の環境構築） |

## フロントエンドテスト

- 設定: `next/vitest.config.ts`
- テストファイル: `next/src/__tests__/`
- 使い方: `next/src/__tests__/README.md`
