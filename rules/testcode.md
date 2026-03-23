# 自動テストの実装ルール

## 絶対に守ること

* **本番データに触れるテストを書かない**
* **テストで外部サービス・実ファイルに副作用を出さない**

---

## テスト方針

| 項目 | ルール |
|------|--------|
| テストフレームワーク | `pytest` |
| 実行コマンド | `uv run pytest` |
| カバレッジ確認 | `uv run pytest --cov=src --cov-report=term-missing` |
| 外部依存の切り離し | `unittest.mock.patch` / `pytest-mock` の `mocker` を使用 |
| ファイルI/O | `tmp_path` フィクスチャ（pytest組み込み）を使用 |
| 環境変数 | `monkeypatch.setenv()` で差し替え |
| 絶対値アサーション | **避ける**（後述） |

---

## 外部依存の切り離し（Mock）

### 原則

テストは **外部に副作用を出さない**。以下は必ずモックで切り離す。

* 外部 API 呼び出し
* ファイル読み書き（実パスへの書き込み）
* データベース接続
* メール・通知送信
* 環境変数

### `patch` の使い方

```python
from unittest.mock import patch

def test_fetch_data_calls_api_once():
    # Given
    with patch("src.client.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"status": "ok"}

        # When
        from src.client import fetch_data
        result = fetch_data("https://example.com/api")

    # Then
    mock_get.assert_called_once()
    assert result["status"] == "ok"
```

### `pytest-mock` の `mocker` を使う場合

```python
def test_send_notification_calls_smtp(mocker):
    # Given
    mock_smtp = mocker.patch("src.notifier.smtplib.SMTP")

    # When
    from src.notifier import send_notification
    send_notification("test@example.com", "件名", "本文")

    # Then
    mock_smtp.assert_called_once()
```

---

## ファイルI/O のテスト

実際のファイルパスに書き込まず、pytest の `tmp_path` フィクスチャを使う。

```python
def test_write_csv_creates_file_with_correct_content(tmp_path):
    # Given
    output_file = tmp_path / "output.csv"
    records = [{"name": "Alice", "amount": 1000}]

    # When
    from src.writer import write_csv
    write_csv(records, output_file)

    # Then
    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    assert "Alice" in content
    assert "1000" in content
```

---

## 環境変数のテスト

`monkeypatch` で環境変数を差し替え、テスト後に自動リセットされる。

```python
def test_load_config_reads_env_variable(monkeypatch):
    # Given
    monkeypatch.setenv("API_KEY", "test-key-12345")

    # When
    from src.config import load_config
    config = load_config()

    # Then
    assert config["api_key"] == "test-key-12345"
```

---

## アサーション方針

### 絶対値アサーションを避ける

外部状態に依存した絶対値での比較は、テスト環境が変わると壊れる。

```python
# NG: 絶対値アサーション
assert len(results) == 5  # 初期データ数が変わると壊れる

# OK: 相対値アサーション
initial_count = len(results_before)
assert len(results_after) == initial_count + 1
```

### 例外のアサーション

```python
import pytest

def test_parse_invalid_csv_raises_value_error():
    # Given
    invalid_data = "not,a,valid\ncsv,format"

    # When / Then
    with pytest.raises(ValueError, match="Invalid CSV format"):
        from src.parser import parse_csv
        parse_csv(invalid_data)
```

### 標準出力のアサーション（CLIツール）

```python
def test_cli_outputs_success_message(capsys):
    # When
    from src.main import run
    run(["--input", "data.csv"])

    # Then
    captured = capsys.readouterr()
    assert "完了" in captured.out
```

---

## テストの種類と対象

### Unit テスト（`tests/unit/`）

単一の関数・クラスの振る舞いを検証する。外部依存はすべてモックする。

```
tests/
└── unit/
    ├── test_parser.py      # データ変換・パース処理
    ├── test_validator.py   # バリデーションロジック
    └── test_formatter.py   # 出力フォーマット処理
```

### Integration テスト（`tests/integration/`）

複数モジュールの連携を検証する。外部サービスはモックするが、内部モジュール間の結合はそのまま使う。

```
tests/
└── integration/
    ├── test_pipeline.py    # CSV読み込み → 変換 → 出力の一連処理
    └── test_cli.py         # CLIコマンドの入出力
```

---

## テスト構成のルール

### ディレクトリ構成

```
tests/
├── __init__.py
├── unit/
│   ├── __init__.py
│   └── test_<module>.py
├── integration/
│   ├── __init__.py
│   └── test_<feature>.py
├── conftest.py             # 共通フィクスチャ
└── test.csv                # テスト仕様書
```

### `conftest.py` の使い方

共通の前提条件（フィクスチャ）はここに定義し、テストファイル間で再利用する。

```python
# tests/conftest.py
import pytest

@pytest.fixture
def sample_records():
    return [
        {"date": "2024-01-01", "amount": 1000, "description": "交通費"},
        {"date": "2024-01-02", "amount": 500,  "description": "消耗品"},
    ]

@pytest.fixture
def temp_csv(tmp_path):
    csv_file = tmp_path / "input.csv"
    csv_file.write_text("date,amount,description\n2024-01-01,1000,交通費\n", encoding="utf-8")
    return csv_file
```

---

## テスト実行前チェックリスト

実装に入る前に、以下を確認する。

1. **仮想環境の確認**: `uv run python --version` でプロジェクトの Python が使われているか
2. **依存パッケージの確認**: `uv sync` で必要パッケージがインストールされているか
3. **既存テストの通過確認**: `uv run pytest` で既存テストがすべて通るか
4. **モック対象の特定**: テスト対象が依存する外部リソースを事前に洗い出しているか