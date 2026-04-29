"""
reconcile.py

りそなデビット明細と仕訳帳を照合し、勘定科目を推定してCSVに書き出す

使い方:
  python -m accounting.reconcile [--journal PATH] [--debit PATH] [--rules PATH] [--output DIR]

省略時のデフォルト:
  --journal: data/accounting/仕訳帳.csv
  --debit:   data/accounting/risona_debit.csv
  --rules:   accounting/rules/merchant_rules.yml
  --output:  data/accounting/output/
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

from .classifier import classify
from .matcher import match

DEFAULT_JOURNAL = Path("data/accounting/仕訳帳.csv")
DEFAULT_DEBIT   = Path("data/accounting/risona_debit.csv")
DEFAULT_RULES   = Path("accounting/rules/merchant_rules.yml")
DEFAULT_OUTPUT  = Path("data/accounting/output")

# 仕訳帳のVISAデビ候補抽出条件
# - 借方/貸方の補助科目がこの口座のもの
# - かつ反対側の勘定科目が「普通預金/現金」以外（口座間振替・現金引出を除外）
RISONA_ACCOUNT = "りそな銀行大手支店普通0073514"
NON_VISA_OPPOSITE = {"普通預金", "現金"}

# りそな明細のステータス分類
# 「確定」のみが仕訳化対象。それ以外は仕訳に入らないので照合対象外として別出力する。
RISONA_STATUS_TARGET   = "確定"
RISONA_STATUS_DECLINED = "決済不可"

COMPACT_COLS = [
    "利用日", "利用内容", "利用内容（入力）", "金額", "承認番号", "ステータス",
    "取引No", "取引日", "借方勘定科目", "借方勘定科目（入力）", "補助科目（入力）", "借方金額(円)",
    "貸方勘定科目", "貸方補助科目", "貸方金額(円)", "摘要",
    "要目視確認",
]


def add_account(df: pd.DataFrame, rules: list) -> pd.DataFrame:
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


def main() -> None:
    # Windows コンソール（CP932）で日本語が化けるのを防ぐ
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        prog="python -m accounting.reconcile",
        description="りそなデビット明細と仕訳帳を照合し、勘定科目を推定してCSVに書き出す",
    )
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL,
                        help=f"freee仕訳帳CSV (default: {DEFAULT_JOURNAL})")
    parser.add_argument("--debit", type=Path, default=DEFAULT_DEBIT,
                        help=f"りそなデビット明細CSV (default: {DEFAULT_DEBIT})")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES,
                        help=f"勘定科目ルールYAML (default: {DEFAULT_RULES})")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help=f"出力ディレクトリ (default: {DEFAULT_OUTPUT})")
    args = parser.parse_args()

    risona_all = pd.read_csv(args.debit,   encoding="cp932", dtype=str).fillna("")
    journal    = pd.read_csv(args.journal, encoding="cp932", dtype=str).fillna("")
    rules      = yaml.safe_load(args.rules.read_text(encoding="utf-8"))["rules"]

    status = risona_all["ステータス"]
    risona          = risona_all[status == RISONA_STATUS_TARGET].reset_index(drop=True)
    risona_declined = risona_all[status == RISONA_STATUS_DECLINED].reset_index(drop=True)
    risona_pending  = risona_all[
        ~status.isin({RISONA_STATUS_TARGET, RISONA_STATUS_DECLINED})
    ].reset_index(drop=True)

    # カード照合のスコープ：りそな普通預金が片側、反対側が普通預金/現金以外
    is_risona_debit  = journal["借方補助科目"] == RISONA_ACCOUNT
    is_risona_credit = journal["貸方補助科目"] == RISONA_ACCOUNT
    journal_card_scope = journal[
        (is_risona_debit  & ~journal["貸方勘定科目"].isin(NON_VISA_OPPOSITE)) |
        (is_risona_credit & ~journal["借方勘定科目"].isin(NON_VISA_OPPOSITE))
    ].reset_index(drop=True)

    result = match(risona, journal_card_scope)

    args.output.mkdir(parents=True, exist_ok=True)

    matched_df = add_account(result.matched, rules)

    # カード照合で消化された取引Noを集計
    consumed_nos: set[str] = set()
    for df in (matched_df, result.duplicates):
        if not df.empty:
            consumed_nos.update(df["取引No"].astype(str))

    # 仕訳帳のみ = 全仕訳帳 - カード照合で消化された取引No
    journal_remaining = journal[
        ~journal["取引No"].astype(str).isin(consumed_nos)
    ].reset_index(drop=True)

    files = {
        "カード_照合済み.csv":   matched_df,
        "カード_重複要確認.csv": result.duplicates,
        "カード_未入力.csv":     add_account(result.risona_only, rules),
        "カード_未確定.csv":     risona_pending,
        "カード_対象外.csv":     risona_declined,
        "仕訳帳のみ.csv":         journal_remaining,
    }

    for filename, df in files.items():
        path = args.output / filename
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"{filename}: {len(df)} 件 → {path}")

    if not matched_df.empty:
        cols = [c for c in COMPACT_COLS if c in matched_df.columns]
        compact_path = args.output / "カード_照合済み_コンパクト.csv"
        matched_df[cols].sort_values("取引日").to_csv(
            compact_path, index=False, encoding="utf-8-sig"
        )
        print(f"カード_照合済み_コンパクト.csv: {len(matched_df)} 件 → {compact_path}")

    # --- 最終評価 ---
    # カード照合の完了判定（重複要確認・未入力が両方0なら〇）
    card_issues = {
        "カード_重複要確認": len(result.duplicates),
        "カード_未入力":     len(result.risona_only),
    }
    card_total = sum(card_issues.values())
    print()
    if card_total == 0:
        print("カード照合: 〇 すべて照合済み")
    else:
        breakdown = ", ".join(f"{k} {v}件" for k, v in card_issues.items() if v > 0)
        print(f"カード照合: × 未解決 {card_total}件（{breakdown}）")
    print(f"仕訳帳のみ: {len(journal_remaining)}件（カード照合外・他ツールでの照合待ち）")


if __name__ == "__main__":
    main()
