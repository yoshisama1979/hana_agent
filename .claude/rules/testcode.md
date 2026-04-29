---
description:
globs:
alwaysApply: false
---

## 自動テストの実装について

- **RefreshDatabase は絶対に使わないこと**

---

### テスト方針

- `SafeTestCase` を使用（本番 DB 保護）
- `DatabaseTransactions` でデータロールバック
- 絶対値アサーションは避け、相対値アサーションを使用
- **TDD 原則**: テストファースト、継続的テスト実行

---

### テスト DB 使用方法

- **SafeTestCase**: 本番 DB 保護機能付きテストベースクラス
  - **本番 DB 名チェック**: 具体的な DB 名を指定（例: stamprally, production, prod, live, main）
  - **testing 環境でのみ実行許可**: `APP_ENV=testing` 必須
  - **SQLite インメモリ使用**: `DB_DATABASE=:memory:` 設定
  - 自動マイグレーション実行
  - TestSeeder で初期データ投入
- **DatabaseTransactions**: 各テスト後にデータロールバック
- **相対値アサーション**: `assertGreaterThanOrEqual($initialCount + 1, $finalCount)` 等を使用
- **データ作成**: 既存データ参照 + 必要に応じて新規作成

---

### テスト実行前の確認

1. **環境確認**: `php artisan config:show database` で DB 設定確認
2. **DB 名確認**: 本番 DB 名が含まれていないか確認
3. **環境変数確認**: `APP_ENV=testing`、`DB_DATABASE=:memory:` 設定確認

---

### テスト作成

- **ユニットテスト**: モデル、リレーション、メソッド
- **フィーチャーテスト**: API、コントローラー、認証
- エラーケース、境界値、セキュリティテストも含む
- テスト実行で失敗を確認（Red）

---

### コード実装

- テストが通る最小限のコードを実装
- テスト実行で成功を確認（Green）
- 必要に応じてリファクタリング（Refactor）

---

### TDD サイクル

仕様書 → テスト作成 → テスト失敗（Red） → コード実装 → テスト成功（Green） → リファクタリング
