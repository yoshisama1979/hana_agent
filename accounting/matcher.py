import re
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class MatchResult:
    matched: pd.DataFrame = field(default_factory=pd.DataFrame)
    duplicates: pd.DataFrame = field(default_factory=pd.DataFrame)
    risona_only: pd.DataFrame = field(default_factory=pd.DataFrame)
    journal_only: pd.DataFrame = field(default_factory=pd.DataFrame)


def _normalize_date(series: pd.Series) -> pd.Series:
    """各種日付フォーマットを YYYY-MM-DD に正規化する。

    対応フォーマット:
      - 2025年04月07日 （りそな）
      - 2025/04/07    （freee仕訳帳）
    """

    def _to_iso(val: str) -> str:
        # 「年月日」形式
        m = re.fullmatch(r"(\d{4})年(\d{2})月(\d{2})日", val.strip())
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        # スラッシュ区切り形式
        m = re.fullmatch(r"(\d{4})/(\d{2})/(\d{2})", val.strip())
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        raise ValueError(f"日付フォーマット不明: {val!r}")

    return series.apply(_to_iso)


def match(risona: pd.DataFrame, journal: pd.DataFrame) -> MatchResult:
    """りそな明細と仕訳帳を金額＋日付で照合し、MatchResult を返す。"""
    r = risona.copy()
    j = journal.copy()

    r["_date"] = _normalize_date(r["利用日"])
    r["_amount"] = r["金額"].astype(str).str.strip()

    j["_date"] = _normalize_date(j["取引日"])
    j["_amount"] = j["借方金額(円)"].astype(str).str.strip()

    r["_key"] = r["_date"] + "_" + r["_amount"]
    j["_key"] = j["_date"] + "_" + j["_amount"]

    all_keys = set(r["_key"]) | set(j["_key"])
    matched_rows: list[pd.DataFrame] = []
    dup_rows: list[pd.DataFrame] = []
    risona_only_rows: list[pd.DataFrame] = []
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
            risona_only_rows.append(r_rows)
        elif rc == 1 and jc == 1:
            # 1:1 一致 → matched
            merged = r_rows.join(j_rows, rsuffix="_journal")
            matched_rows.append(merged)
        else:
            # N:N（N>1）または件数不一致 → duplicates（ペアとして結合）
            for i in range(min(rc, jc)):
                pair = (
                    r_rows.iloc[[i]]
                    .reset_index(drop=True)
                    .join(j_rows.iloc[[i]].reset_index(drop=True), rsuffix="_journal")
                )
                dup_rows.append(pair)
            # 余剰分は未照合へ
            if rc > jc:
                risona_only_rows.append(r_rows.iloc[jc:].reset_index(drop=True))
            elif jc > rc:
                journal_only_rows.append(j_rows.iloc[rc:].reset_index(drop=True))

    def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    return MatchResult(
        matched=_concat(matched_rows),
        duplicates=_concat(dup_rows),
        risona_only=_concat(risona_only_rows),
        journal_only=_concat(journal_only_rows),
    )
