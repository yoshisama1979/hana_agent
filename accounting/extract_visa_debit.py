"""
extract_visa_debit.py

仕訳帳CSVから以下の条件に合う行を抽出してCSVに書き出す
  - 借方勘定科目 が「★要確認」
  - 摘要 が「VISAデビ」で始まる

使い方:
  python extract_visa_debit.py [入力CSVパス] [出力CSVパス]

省略時のデフォルト:
  入力: data/仕訳帳.csv
  出力: data/output/visa_debit_要確認.csv
"""

import sys
import pandas as pd
from pathlib import Path

# --- パス設定 ---
BASE_DIR = Path(__file__).parent
input_file  = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE_DIR / "data" / "仕訳帳.csv"
output_file = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE_DIR / "data" / "output" / "visa_debit_要確認.csv"

# --- 読み込み ---
df = pd.read_csv(input_file, encoding="cp932", dtype=str).fillna("")

# --- フィルタリング ---
mask = (df["借方勘定科目"] == "★要確認") & df["摘要"].str.startswith("VISAデビ")
result = df[mask]

# --- 書き出し ---
output_file.parent.mkdir(parents=True, exist_ok=True)
result.to_csv(output_file, index=False, encoding="utf-8-sig")

print(f"完了: {len(result)} 件を抽出しました")
print(f"出力先: {output_file}")
