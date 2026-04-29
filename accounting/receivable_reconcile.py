"""
receivable_reconcile.py

売掛金（売上計上時の借方=売掛金）と入金（回収時の貸方=売掛金）を、
仕訳帳内で 補助科目 + 金額 によりペアリングして消し込む。

- 補助科目（取引先）が空欄の行は対象外（取引先未特定なので誤マッチを避ける）
- ペアは「請求日 < 入金日」を厳格に守る（同日・前払いは作らない）
- 同じ補助科目・同金額に複数候補がある場合、取引日昇順で1:1にペアリング
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

RECEIVABLE_ACCOUNT = "売掛金"


@dataclass
class ReceivableMatchResult:
    matched: pd.DataFrame = field(default_factory=pd.DataFrame)
    consumed_journal_nos: set[str] = field(default_factory=set)


def _normalize_amount(value) -> int:
    """カンマ・小数を取り除いて符号なし整数を返す。空文字・NaNは0扱い。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0
    s = str(value).replace(",", "").strip()
    if not s or s.lower() == "nan":
        return 0
    return int(abs(float(s)))


def reconcile_receivables(journal: pd.DataFrame) -> ReceivableMatchResult:
    """仕訳帳から売掛金の請求⇄入金ペアを抽出して返す。"""
    j = journal.copy()
    j["_amount_d"] = j["借方金額(円)"].apply(_normalize_amount)
    j["_amount_c"] = j["貸方金額(円)"].apply(_normalize_amount)

    is_invoice = (
        (j["借方勘定科目"] == RECEIVABLE_ACCOUNT)
        & (j["借方補助科目"].astype(str).str.strip() != "")
    )
    is_deposit = (
        (j["貸方勘定科目"] == RECEIVABLE_ACCOUNT)
        & (j["貸方補助科目"].astype(str).str.strip() != "")
    )

    invoices = j[is_invoice].copy()
    invoices["_subj"] = invoices["借方補助科目"]
    invoices["_amt"] = invoices["_amount_d"]

    deposits = j[is_deposit].copy()
    deposits["_subj"] = deposits["貸方補助科目"]
    deposits["_amt"] = deposits["_amount_c"]

    # 取引日を datetime に正規化（昇順ソート用）
    invoices["_dt"] = pd.to_datetime(
        invoices["取引日"], format="%Y/%m/%d", errors="coerce",
    )
    deposits["_dt"] = pd.to_datetime(
        deposits["取引日"], format="%Y/%m/%d", errors="coerce",
    )

    pair_rows: list[dict] = []
    consumed: set[str] = set()

    keys = set(invoices.groupby(["_subj", "_amt"]).groups.keys()) & set(
        deposits.groupby(["_subj", "_amt"]).groups.keys()
    )
    for subj, amt in keys:
        invoice_group = invoices[
            (invoices["_subj"] == subj) & (invoices["_amt"] == amt)
        ].sort_values("_dt").reset_index(drop=True)
        deposit_group = deposits[
            (deposits["_subj"] == subj) & (deposits["_amt"] == amt)
        ].sort_values("_dt").reset_index(drop=True)

        used_deposit_idx: set[int] = set()
        for _, inv in invoice_group.iterrows():
            for d_idx, dep in deposit_group.iterrows():
                if d_idx in used_deposit_idx:
                    continue
                if pd.isna(inv["_dt"]) or pd.isna(dep["_dt"]):
                    continue
                if dep["_dt"] <= inv["_dt"]:
                    continue
                pair_rows.append({
                    "請求_取引No": str(inv["取引No"]),
                    "請求_取引日": inv["取引日"],
                    "請求_借方金額(円)": inv["借方金額(円)"],
                    "補助科目": subj,
                    "請求_摘要": inv.get("摘要", ""),
                    "入金_取引No": str(dep["取引No"]),
                    "入金_取引日": dep["取引日"],
                    "入金_貸方金額(円)": dep["貸方金額(円)"],
                    "入金_摘要": dep.get("摘要", ""),
                })
                consumed.add(str(inv["取引No"]))
                consumed.add(str(dep["取引No"]))
                used_deposit_idx.add(d_idx)
                break

    matched_df = pd.DataFrame(pair_rows) if pair_rows else pd.DataFrame()
    return ReceivableMatchResult(matched=matched_df, consumed_journal_nos=consumed)
