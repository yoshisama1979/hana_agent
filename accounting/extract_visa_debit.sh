#!/bin/bash

# extract_visa_debit.sh
# 仕訳帳CSVからVISAデビット（★要確認）の行を抽出する

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# .env からPATHを読み込む
if [ -f "$ROOT_DIR/.env" ]; then
  export $(grep -v '^#' "$ROOT_DIR/.env" | xargs)
fi

if [ -z "$PYTHON" ]; then
  echo "エラー: .env に PYTHON が設定されていません"
  exit 1
fi

PY_SCRIPT="$SCRIPT_DIR/extract_visa_debit.py"
PYTHONIOENCODING=utf-8 "$PYTHON" "$PY_SCRIPT" "$@"
