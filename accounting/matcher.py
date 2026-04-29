import re
from dataclasses import dataclass, field
from datetime import date

import pandas as pd


# 照合処理の中で一時的に付与する内部マーカ列。出力前に必ず drop する。
_INTERNAL_COLS: list[str] = ["_date", "_amount", "_key", "_dt"]


@dataclass
class MatchResult:
    matched: pd.DataFrame = field(default_factory=pd.DataFrame)
    duplicates: pd.DataFrame = field(default_factory=pd.DataFrame)
    debit_only: pd.DataFrame = field(default_factory=pd.DataFrame)
    journal_only: pd.DataFrame = field(default_factory=pd.DataFrame)


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """空でない DataFrame リストを結合する。空なら空 DataFrame を返す。"""
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


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


def _to_date(iso: str) -> date:
    """YYYY-MM-DD 形式の文字列を date オブジェクトに変換する。"""
    y, m, d = iso.split("-")
    return date(int(y), int(m), int(d))


def match(
    debit: pd.DataFrame,
    journal: pd.DataFrame,
    *,
    debit_date_col: str = "利用日",
    debit_amount_col: str = "金額",
    date_tolerance_days: int = 0,
    offsets: list[int] | None = None,
) -> MatchResult:
    """カード明細と仕訳帳を金額＋日付で照合し、MatchResult を返す。

    debit_date_col / debit_amount_col でカード固有のカラム名を指定できる。
    date_tolerance_days > 0 を指定すると、日付ズレ0日 → 1日 → ... → N日 と
    段階的にマッチングを行い、ズレの少ないペアから順に消化する。

    offsets を指定すると、その値リストの順序でマッチングを行う。
    たとえば offsets=[0] で段階0のみ、offsets=[2] で段階2のみ実行する。
    呼び出し側で「段階×戦略」の入れ子ループを構成する用途で使う。
    """
    iter_offsets = offsets if offsets is not None else range(date_tolerance_days + 1)
    r = debit.copy().reset_index(drop=True)
    j = journal.copy().reset_index(drop=True)

    r["_date"] = _normalize_date(r[debit_date_col])
    r["_amount"] = _normalize_amount(r[debit_amount_col])
    j["_date"] = _normalize_date(j["取引日"])
    j["_amount"] = _normalize_amount(j["借方金額(円)"])
    r["_dt"] = r["_date"].apply(_to_date)
    j["_dt"] = j["_date"].apply(_to_date)

    matched_chunks: list[pd.DataFrame] = []
    dup_chunks: list[pd.DataFrame] = []
    used_r: set = set()
    used_j: set = set()

    for offset in iter_offsets:
        r_remaining = r[~r.index.isin(used_r)]
        j_remaining = j[~j.index.isin(used_j)]
        if r_remaining.empty or j_remaining.empty:
            continue

        if offset == 0:
            stage_matched, stage_dup, paired_r, paired_j = _match_exact(
                r_remaining, j_remaining,
            )
        else:
            stage_matched, stage_dup, paired_r, paired_j = _match_with_offset(
                r_remaining, j_remaining, offset,
            )

        for df in (stage_matched, stage_dup):
            if not df.empty:
                df["照合方法"] = "完全一致" if offset == 0 else "日付ズレ"
                df["日付ズレ日数"] = offset

        if not stage_matched.empty:
            matched_chunks.append(stage_matched)
        if not stage_dup.empty:
            dup_chunks.append(stage_dup)
        used_r.update(paired_r)
        used_j.update(paired_j)

    debit_only = r[~r.index.isin(used_r)].drop(columns=_INTERNAL_COLS, errors="ignore").reset_index(drop=True)
    journal_only = j[~j.index.isin(used_j)].drop(columns=_INTERNAL_COLS, errors="ignore").reset_index(drop=True)

    return MatchResult(
        matched=_concat(matched_chunks),
        duplicates=_concat(dup_chunks),
        debit_only=debit_only,
        journal_only=journal_only,
    )


def _match_exact(
    r: pd.DataFrame, j: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, list, list]:
    """段階0：同日・同金額でグループ化し、件数一致なら 1:1 / N:N、不一致は重複要確認。"""
    r = r.copy()
    j = j.copy()
    r["_key"] = r["_date"] + "_" + r["_amount"]
    j["_key"] = j["_date"] + "_" + j["_amount"]

    matched_rows: list[pd.DataFrame] = []
    dup_rows: list[pd.DataFrame] = []
    paired_r: list = []
    paired_j: list = []

    for key in set(r["_key"]) & set(j["_key"]):
        r_rows = r[r["_key"] == key]
        j_rows = j[j["_key"] == key]
        rc, jc = len(r_rows), len(j_rows)

        r_clean = r_rows.drop(columns=_INTERNAL_COLS, errors="ignore").reset_index(drop=True)
        j_clean = j_rows.drop(columns=_INTERNAL_COLS, errors="ignore").reset_index(drop=True)

        if rc == jc:
            needs_review = rc > 1
            for i in range(rc):
                pair = (
                    r_clean.iloc[[i]].reset_index(drop=True)
                    .join(j_clean.iloc[[i]].reset_index(drop=True), rsuffix="_journal")
                )
                pair["要目視確認"] = "要確認" if needs_review else ""
                matched_rows.append(pair)
            paired_r.extend(r_rows.index.tolist())
            paired_j.extend(j_rows.index.tolist())
        else:
            n = min(rc, jc)
            for i in range(n):
                pair = (
                    r_clean.iloc[[i]].reset_index(drop=True)
                    .join(j_clean.iloc[[i]].reset_index(drop=True), rsuffix="_journal")
                )
                pair["要目視確認"] = ""
                dup_rows.append(pair)
            # 件数不一致時は少ない方の件数だけ paired として消費する
            if rc <= jc:
                paired_r.extend(r_rows.index.tolist())
                paired_j.extend(j_rows.index.tolist()[:n])
            else:
                paired_r.extend(r_rows.index.tolist()[:n])
                paired_j.extend(j_rows.index.tolist())

    return _concat(matched_rows), _concat(dup_rows), paired_r, paired_j


def _match_with_offset(
    r: pd.DataFrame, j: pd.DataFrame, offset: int,
) -> tuple[pd.DataFrame, pd.DataFrame, list, list]:
    """段階1以上：金額一致＆|日付差|==offset の行同士を greedy に1:1ペアリング。"""
    matched_rows: list[pd.DataFrame] = []
    paired_r: list = []
    paired_j: list = []
    used_j_idx: set = set()

    for r_idx, r_row in r.iterrows():
        for j_idx, j_row in j.iterrows():
            if j_idx in used_j_idx:
                continue
            if r_row["_amount"] != j_row["_amount"]:
                continue
            if abs((r_row["_dt"] - j_row["_dt"]).days) != offset:
                continue
            r_clean = r.loc[[r_idx]].drop(columns=_INTERNAL_COLS, errors="ignore").reset_index(drop=True)
            j_clean = j.loc[[j_idx]].drop(columns=_INTERNAL_COLS, errors="ignore").reset_index(drop=True)
            pair = r_clean.join(j_clean, rsuffix="_journal")
            pair["要目視確認"] = ""
            matched_rows.append(pair)
            paired_r.append(r_idx)
            paired_j.append(j_idx)
            used_j_idx.add(j_idx)
            break

    return _concat(matched_rows), pd.DataFrame(), paired_r, paired_j
