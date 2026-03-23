"""
reconcile.py

りそなデビット明細と仕訳帳を照合し、勘定科目を推定してCSVに書き出す

使い方:
  python reconcile.py [りそな明細CSV] [仕訳帳CSV] [ルールYAML]

省略時のデフォルト:
  りそな明細: data/risona_debit.csv
  仕訳帳:     data/仕訳帳.csv
  ルール:     rules/merchant_rules.yml
"""

import sys
from pathlib import Path

import pandas as pd
import yaml

from .classifier import classify
from .matcher import match

BASE_DIR = Path(__file__).parent

input_risona  = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE_DIR / "data" / "risona_debit.csv"
input_journal = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE_DIR / "data" / "仕訳帳.csv"
rules_file    = Path(sys.argv[3]) if len(sys.argv) > 3 else BASE_DIR / "rules" / "merchant_rules.yml"
output_dir    = BASE_DIR / "data" / "output"

# --- 読み込み ---
risona  = pd.read_csv(input_risona,  encoding="cp932", dtype=str).fillna("")
journal = pd.read_csv(input_journal, encoding="cp932", dtype=str).fillna("")
rules   = yaml.safe_load(rules_file.read_text(encoding="utf-8"))["rules"]

# VISAデビ かつ ★要確認 の行のみ対象
journal = journal[
    journal["摘要"].str.startswith("VISAデビ")
].reset_index(drop=True)

# --- 照合 ---
result = match(risona, journal)

# --- 勘定科目推定（照合済み・りそなのみ に適用）---
def add_account(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    classified = df["利用内容"].apply(lambda m: classify(m, rules))
    df = df.copy()
    df["推定入力名"]   = classified.apply(lambda c: c["入力名"])
    df["推定勘定科目"] = classified.apply(lambda c: c["勘定科目"])
    df["推定補助科目"] = classified.apply(lambda c: c["補助科目"])
    df["推定税区分"]   = classified.apply(lambda c: c["税区分"])
    matched = df["推定勘定科目"] != "★要確認"
    df["利用内容（入力）"]     = df["推定入力名"].where(matched, "")
    df["借方勘定科目（入力）"] = df["推定勘定科目"].where(matched, "")
    df["補助科目（入力）"]     = df["推定補助科目"].where(matched, "")
    return df

# --- 書き出し ---
output_dir.mkdir(parents=True, exist_ok=True)

files = {
    "照合済み.csv":       add_account(result.matched),
    "重複要確認.csv":     result.duplicates,
    "りそなのみ.csv":     add_account(result.risona_only),
    "仕訳帳のみ.csv":     result.journal_only,
}

COMPACT_COLS = [
    "利用日", "利用内容", "利用内容（入力）", "金額", "承認番号", "ステータス",
    "取引No", "取引日", "借方勘定科目", "借方勘定科目（入力）", "補助科目（入力）", "借方金額(円)",
    "貸方勘定科目", "貸方補助科目", "貸方金額(円)", "摘要",
    "要目視確認",
]

for filename, df in files.items():
    path = output_dir / filename
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"{filename}: {len(df)} 件 → {path}")

# --- 照合済みのコンパクト版 ---
matched_df = add_account(result.matched)
if not matched_df.empty:
    cols = [c for c in COMPACT_COLS if c in matched_df.columns]
    compact_path = output_dir / "照合済み_コンパクト.csv"
    matched_df[cols].sort_values("取引日").to_csv(compact_path, index=False, encoding="utf-8-sig")
    print(f"照合済み_コンパクト.csv: {len(matched_df)} 件 → {compact_path}")
