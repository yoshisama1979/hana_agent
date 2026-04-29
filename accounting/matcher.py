import re
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class MatchResult:
    matched: pd.DataFrame = field(default_factory=pd.DataFrame)
    duplicates: pd.DataFrame = field(default_factory=pd.DataFrame)
    debit_only: pd.DataFrame = field(default_factory=pd.DataFrame)
    journal_only: pd.DataFrame = field(default_factory=pd.DataFrame)


def _normalize_date(series: pd.Series) -> pd.Series:
    """各種日付フォーマットを YYYY-MM-DD に正規化する。

    対応フォーマット:
      - 2025年04月07日 （りそな）
      - 2025/04/07    （SBI／freee仕訳帳）
    """

    def _to_iso(val: str) -> str:
        s = val.strip()
        for pattern in (r"(\d{4})年(\d{2})月(\d{2})日", r"(\d{4})/(\d{2})/(\d{2})"):
            m = re.fullmatch(pattern, s)
            if m:
                return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        raise ValueError(f"日付フォーマット不明: {val!r}")

    return series.apply(_to_iso)


def _normalize_amount(series: pd.Series) -> pd.Series:
    """金額を符号なし整数文字列に正規化する。

    明細CSV側は返金がマイナス値、仕訳帳は借方/貸方で方向を表現し金額は正値、
    という表記差があるため絶対値で比較する。
    SBI明細は "400.00" のような小数表記なので float 経由で整数化する。
    """
    return (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.strip()
        .astype(float)
        .abs()
        .astype(int)
        .astype(str)
    )


def match(
    debit: pd.DataFrame,
    journal: pd.DataFrame,
    *,
    debit_date_col: str = "利用日",
    debit_amount_col: str = "金額",
) -> MatchResult:
    """カード明細と仕訳帳を金額＋日付で照合し、MatchResult を返す。

    debit_date_col / debit_amount_col でカード固有のカラム名を指定できる。
    デフォルトはりそなの "利用日" / "金額"。
    """
    r = debit.copy()
    j = journal.copy()

    r["_date"] = _normalize_date(r[debit_date_col])
    r["_amount"] = _normalize_amount(r[debit_amount_col])

    j["_date"] = _normalize_date(j["取引日"])
    j["_amount"] = _normalize_amount(j["借方金額(円)"])

    r["_key"] = r["_date"] + "_" + r["_amount"]
    j["_key"] = j["_date"] + "_" + j["_amount"]

    all_keys = set(r["_key"]) | set(j["_key"])
    matched_rows: list[pd.DataFrame] = []
    dup_rows: list[pd.DataFrame] = []
    debit_only_rows: list[pd.DataFrame] = []
    journal_only_rows: list[pd.DataFrame] = []

    drop_cols = ["_date", "_amount", "_key"]

    for key in all_keys:
        r_rows = r[r["_key"] == key].drop(columns=drop_cols).reset_index(drop=True)
        j_rows = j[j["_key"] == key].drop(columns=drop_cols).reset_index(drop=True)
        rc = len(r_rows)
        jc = len(j_rows)

        if rc == 0:
            journal_only_rows.append(j_rows)
        elif jc == 0:
            debit_only_rows.append(r_rows)
        elif rc == jc:
            # 件数一致（1:1 または N:N）→ matched（N:N は要目視フラグ付き）
            needs_review = rc > 1
            for i in range(rc):
                pair = (
                    r_rows.iloc[[i]]
                    .reset_index(drop=True)
                    .join(j_rows.iloc[[i]].reset_index(drop=True), rsuffix="_journal")
                )
                pair["要目視確認"] = "要確認" if needs_review else ""
                matched_rows.append(pair)
        else:
            # 件数不一致 → duplicates＋余剰は未照合へ
            for i in range(min(rc, jc)):
                pair = (
                    r_rows.iloc[[i]]
                    .reset_index(drop=True)
                    .join(j_rows.iloc[[i]].reset_index(drop=True), rsuffix="_journal")
                )
                dup_rows.append(pair)
            if rc > jc:
                debit_only_rows.append(r_rows.iloc[jc:].reset_index(drop=True))
            elif jc > rc:
                journal_only_rows.append(j_rows.iloc[rc:].reset_index(drop=True))

    def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    return MatchResult(
        matched=_concat(matched_rows),
        duplicates=_concat(dup_rows),
        debit_only=_concat(debit_only_rows),
        journal_only=_concat(journal_only_rows),
    )
