"""
reconcile.py

複数のデビットカード明細と仕訳帳を照合し、勘定科目を推定してCSVに書き出す。

使い方:
  python -m accounting.reconcile [--journal PATH] [--rules PATH] [--output DIR]

省略時のデフォルト:
  --journal: data/accounting/仕訳帳.csv
  --rules:   accounting/rules/merchant_rules.yml
  --output:  data/accounting/output/

明細CSVのパスは accounting/card_profiles.py の各 CardProfile で定義する。
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from .card_profiles import PROFILES, CardProfile
from .classifier import classify
from .matcher import MatchResult, match

DEFAULT_JOURNAL = Path("data/accounting/仕訳帳.csv")
DEFAULT_RULES   = Path("accounting/rules/merchant_rules.yml")
DEFAULT_OUTPUT  = Path("data/accounting/output")

# 仕訳帳のカード照合スコープから除外する反対側勘定科目
NON_VISA_OPPOSITE = {"普通預金", "現金"}

# りそな等のステータス列を持つカードでの分類
STATUS_TARGET   = "確定"
STATUS_DECLINED = "決済不可"

# カード_照合済み_コンパクト.csv のカラム順
# りそな由来とSBI由来でカラム名が異なるため、両方を列挙して存在分のみ抽出する
COMPACT_COLS = [
    # 共通：仕訳帳側
    "取引No", "取引日",
    # 明細側（カード固有）
    "利用日", "利用内容", "金額", "承認番号", "ステータス",        # りそな
    "お取引日", "お取引内容", "お取引金額",                         # SBI
    "利用内容（入力）",
    "借方勘定科目", "借方勘定科目（入力）", "補助科目（入力）", "借方金額(円)",
    "貸方勘定科目", "貸方補助科目", "貸方金額(円)", "摘要",
    "要目視確認", "照合方法", "日付ズレ日数", "金額種別",
]


@dataclass
class CardReport:
    profile: CardProfile
    matched: pd.DataFrame
    duplicates: pd.DataFrame
    debit_only: pd.DataFrame
    pending: pd.DataFrame    # 未確定（ステータスありのみ）
    declined: pd.DataFrame   # 決済不可（ステータスありのみ）

    @property
    def consumed_journal_nos(self) -> set[str]:
        """仕訳帳のみ.csv 集計のために除外する取引No集合"""
        nos: set[str] = set()
        for df in (self.matched, self.duplicates):
            if not df.empty and "取引No" in df.columns:
                nos.update(df["取引No"].astype(str))
        return nos


def _add_account(df: pd.DataFrame, merchant_col: str, rules: list) -> pd.DataFrame:
    """利用内容カラムから勘定科目を推定し、列を追加する"""
    if df.empty:
        return df
    classified = df[merchant_col].apply(lambda m: classify(m, rules))
    df = df.copy()
    df["推定入力名"]   = classified.apply(lambda c: c["入力名"])
    df["推定勘定科目"] = classified.apply(lambda c: c["勘定科目"])
    df["推定補助科目"] = classified.apply(lambda c: c["補助科目"])
    df["推定税区分"]   = classified.apply(lambda c: c["税区分"])
    matched = df["推定勘定科目"] != "★ルール未登録"
    df["利用内容（入力）"]     = df["推定入力名"].where(matched, "")
    df["借方勘定科目（入力）"] = df["推定勘定科目"].where(matched, "")
    df["補助科目（入力）"]     = df["推定補助科目"].where(matched, "")
    return df


def _filter_by_status(
    debit_all: pd.DataFrame, profile: CardProfile,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """ステータスで明細を確定/未確定/決済不可に振り分ける。
    ステータス列のないカードは debit_all をそのまま「確定」、他は空 DataFrame を返す。
    """
    if not profile.has_status or "ステータス" not in debit_all.columns:
        return debit_all.reset_index(drop=True), pd.DataFrame(), pd.DataFrame()

    status = debit_all["ステータス"]
    target   = debit_all[status == STATUS_TARGET].reset_index(drop=True)
    declined = debit_all[status == STATUS_DECLINED].reset_index(drop=True)
    pending  = debit_all[
        ~status.isin({STATUS_TARGET, STATUS_DECLINED})
    ].reset_index(drop=True)
    return target, pending, declined


def _journal_card_scope(journal: pd.DataFrame, profile: CardProfile) -> pd.DataFrame:
    """指定カードの照合対象となる仕訳帳行（反対側が普通預金/現金以外）を抽出"""
    is_debit  = journal["借方補助科目"] == profile.account_name
    is_credit = journal["貸方補助科目"] == profile.account_name
    return journal[
        (is_debit  & ~journal["貸方勘定科目"].isin(NON_VISA_OPPOSITE)) |
        (is_credit & ~journal["借方勘定科目"].isin(NON_VISA_OPPOSITE))
    ].reset_index(drop=True)


def reconcile_card(
    profile: CardProfile, journal: pd.DataFrame, rules: list,
) -> tuple[CardReport, MatchResult]:
    """1カード分を照合し、CardReport と生の MatchResult を返す。

    profile.fee_cols が指定されている場合、パス1（本体金額のみ）で残った debit_only に対し、
    パス2（本体+手数料の合算金額）で再照合する。
    """
    debit_all = profile.load_debit()
    debit_target, pending, declined = _filter_by_status(debit_all, profile)

    journal_scope = _journal_card_scope(journal, profile)

    # パス1：本体金額のみで段階マッチング
    pass1 = match(
        debit_target, journal_scope,
        debit_date_col=profile.date_col,
        debit_amount_col=profile.amount_col,
        date_tolerance_days=profile.date_tolerance_days,
    )
    matched_chunks = [_tag_amount_kind(pass1.matched, "本体")]
    duplicates_chunks = [_tag_amount_kind(pass1.duplicates, "本体")]
    debit_only_remaining = pass1.debit_only
    journal_only_remaining = pass1.journal_only

    # パス2：本体+手数料の合算金額で再照合（fee_cols 指定時のみ）
    if profile.fee_cols and not debit_only_remaining.empty:
        debit_with_fee, original_amount_col_backup = _build_fee_inclusive_debit(
            debit_only_remaining, profile,
        )
        if not debit_with_fee.empty:
            pass2 = match(
                debit_with_fee, journal_only_remaining,
                debit_date_col=profile.date_col,
                debit_amount_col=profile.amount_col,
                date_tolerance_days=profile.date_tolerance_days,
            )
            # パス2でマッチした行は元の金額列に戻してから出力する
            pass2_matched = _restore_original_amount(
                pass2.matched, profile.amount_col, original_amount_col_backup,
            )
            pass2_duplicates = _restore_original_amount(
                pass2.duplicates, profile.amount_col, original_amount_col_backup,
            )
            pass2_debit_only = _restore_original_amount(
                pass2.debit_only, profile.amount_col, original_amount_col_backup,
            )
            matched_chunks.append(_tag_amount_kind(pass2_matched, "本体+手数料"))
            duplicates_chunks.append(_tag_amount_kind(pass2_duplicates, "本体+手数料"))
            # パス2対象外（手数料0の行）と パス2でも未消化の行を再合流
            debit_excluded = debit_only_remaining[
                ~debit_only_remaining.index.isin(debit_with_fee.index)
            ]
            debit_only_remaining = pd.concat(
                [debit_excluded, pass2_debit_only], ignore_index=True,
            )
            journal_only_remaining = pass2.journal_only

    matched_all     = _concat_nonempty(matched_chunks)
    duplicates_all  = _concat_nonempty(duplicates_chunks)

    matched_df    = _add_account(matched_all, profile.merchant_col, rules)
    debit_only_df = _add_account(debit_only_remaining, profile.merchant_col, rules)

    report = CardReport(
        profile=profile,
        matched=matched_df,
        duplicates=duplicates_all,
        debit_only=debit_only_df,
        pending=pending,
        declined=declined,
    )
    # 後方互換用に末尾の MatchResult は journal_only のみ意味を保つ
    final_result = MatchResult(
        matched=matched_all,
        duplicates=duplicates_all,
        debit_only=debit_only_remaining,
        journal_only=journal_only_remaining,
    )
    return report, final_result


_AMOUNT_BACKUP_COL = "_original_amount"


def _build_fee_inclusive_debit(
    debit_only: pd.DataFrame, profile: CardProfile,
) -> tuple[pd.DataFrame, str]:
    """パス2用に「本体+手数料」金額列を上書きした DataFrame を返す。

    対象は fee_cols のいずれかが0より大きい行のみ。元の金額は _original_amount に退避。
    """
    df = debit_only.copy()
    fees_total = sum(df[c].astype(float) for c in profile.fee_cols)
    has_fee = fees_total > 0
    df = df[has_fee].copy()
    if df.empty:
        return df, _AMOUNT_BACKUP_COL

    df[_AMOUNT_BACKUP_COL] = df[profile.amount_col]
    df[profile.amount_col] = (
        df[profile.amount_col].astype(float) + fees_total[has_fee]
    ).astype(str)
    return df, _AMOUNT_BACKUP_COL


def _restore_original_amount(
    df: pd.DataFrame, amount_col: str, backup_col: str,
) -> pd.DataFrame:
    """パス2用に上書きした金額列を元の値に戻す。"""
    if df.empty or backup_col not in df.columns:
        return df
    df = df.copy()
    df[amount_col] = df[backup_col]
    df = df.drop(columns=[backup_col], errors="ignore")
    return df


def _tag_amount_kind(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    """金額種別列を付与する。空 DataFrame はそのまま返す。"""
    if df.empty:
        return df
    df = df.copy()
    df["金額種別"] = kind
    return df


def _concat_nonempty(frames: list[pd.DataFrame]) -> pd.DataFrame:
    nonempty = [f for f in frames if not f.empty]
    return pd.concat(nonempty, ignore_index=True) if nonempty else pd.DataFrame()


def _write_card_outputs(report: CardReport, output_dir: Path) -> None:
    """1カード分の出力CSVを output_dir/<card_id>/ 配下に書き出す"""
    card_dir = output_dir / report.profile.card_id
    card_dir.mkdir(parents=True, exist_ok=True)

    files: dict[str, pd.DataFrame] = {
        "カード_照合済み.csv":   report.matched,
        "カード_重複要確認.csv": report.duplicates,
        "カード_未入力.csv":     report.debit_only,
    }
    if report.profile.has_status:
        files["カード_未確定.csv"] = report.pending
        files["カード_対象外.csv"] = report.declined

    for filename, df in files.items():
        path = card_dir / filename
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"[{report.profile.card_id}] {filename}: {len(df)} 件 → {path}")

    if not report.matched.empty:
        cols = [c for c in COMPACT_COLS if c in report.matched.columns]
        compact_path = card_dir / "カード_照合済み_コンパクト.csv"
        report.matched[cols].sort_values("取引日").to_csv(
            compact_path, index=False, encoding="utf-8-sig",
        )
        print(
            f"[{report.profile.card_id}] カード_照合済み_コンパクト.csv: "
            f"{len(report.matched)} 件 → {compact_path}"
        )


def _print_summary(reports: list[CardReport], journal_only_count: int) -> None:
    print()
    for report in reports:
        issues = {
            "カード_重複要確認": len(report.duplicates),
            "カード_未入力":     len(report.debit_only),
        }
        total = sum(issues.values())
        if total == 0:
            print(f"カード照合({report.profile.card_id}): 〇 すべて照合済み")
        else:
            print(f"カード照合({report.profile.card_id}): × 未解決 {total}件")

        # 金額種別 × 段階（日付ズレ日数）別の消化件数を表示
        if (
            not report.matched.empty
            and "日付ズレ日数" in report.matched.columns
            and "金額種別" in report.matched.columns
        ):
            grouped = (
                report.matched.assign(
                    _offset=report.matched["日付ズレ日数"].astype(int)
                )
                .groupby(["金額種別", "_offset"])
                .size()
                .sort_index()
            )
            for (kind, offset), count in grouped.items():
                stage = "完全一致" if offset == 0 else f"日付ズレ ±{offset}日"
                print(f"  {kind} {stage}: {count}件")

        for key, value in issues.items():
            if value > 0:
                print(f"  {key}: {value}件")

    print(f"仕訳帳のみ: {journal_only_count}件（カード照合外・他ツールでの照合待ち）")


def run(
    *,
    profiles: list[CardProfile],
    journal: Path,
    rules: Path,
    output: Path,
) -> list[CardReport]:
    """全カードを順に照合し、結果CSVを output 配下に書き出す"""
    journal_df = pd.read_csv(journal, encoding="cp932", dtype=str).fillna("")
    rules_list = yaml.safe_load(rules.read_text(encoding="utf-8"))["rules"]

    output.mkdir(parents=True, exist_ok=True)

    reports: list[CardReport] = []
    consumed_nos: set[str] = set()
    for profile in profiles:
        report, _ = reconcile_card(profile, journal_df, rules_list)
        _write_card_outputs(report, output)
        reports.append(report)
        consumed_nos |= report.consumed_journal_nos

    journal_remaining = journal_df[
        ~journal_df["取引No"].astype(str).isin(consumed_nos)
    ].reset_index(drop=True)
    journal_only_path = output / "仕訳帳のみ.csv"
    journal_remaining.to_csv(journal_only_path, index=False, encoding="utf-8-sig")
    print(f"仕訳帳のみ.csv: {len(journal_remaining)} 件 → {journal_only_path}")

    _print_summary(reports, len(journal_remaining))
    return reports


def main() -> None:
    # Windows コンソール（CP932）で日本語が化けるのを防ぐ
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        prog="python -m accounting.reconcile",
        description="複数のデビットカード明細と仕訳帳を照合し、勘定科目を推定してCSVに書き出す",
    )
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL,
                        help=f"freee仕訳帳CSV (default: {DEFAULT_JOURNAL})")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES,
                        help=f"勘定科目ルールYAML (default: {DEFAULT_RULES})")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help=f"出力ディレクトリ (default: {DEFAULT_OUTPUT})")
    args = parser.parse_args()

    run(
        profiles=list(PROFILES.values()),
        journal=args.journal,
        rules=args.rules,
        output=args.output,
    )


if __name__ == "__main__":
    main()
