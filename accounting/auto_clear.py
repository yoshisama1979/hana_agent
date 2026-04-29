"""
auto_clear.py

YAMLルールにマッチする「明らかに正しい」仕訳帳行を一括消化する。
カード照合・売掛金照合のような相方とのペアリングは行わず、
単に「確認不要」として仕訳帳のみ.csv から除外することを目的とする。

ルールの各条件はすべて任意で、指定された条件のみ AND 結合で判定する。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

# ルールYAMLで指定可能な条件キー
_EXACT_KEYS: tuple[str, ...] = (
    "借方勘定科目", "借方補助科目",
    "貸方勘定科目", "貸方補助科目",
)
_AMOUNT_KEYS: dict[str, str] = {
    "借方金額": "借方金額(円)",
    "貸方金額": "貸方金額(円)",
}
_REGEX_KEY = "摘要正規表現"


@dataclass
class AutoClearResult:
    cleared: pd.DataFrame = field(default_factory=pd.DataFrame)
    consumed_journal_nos: set[str] = field(default_factory=set)


def _normalize_amount(value) -> int | None:
    """金額カラムを符号なし整数に正規化する。空文字は None。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).replace(",", "").strip()
    if not s or s.lower() == "nan":
        return None
    try:
        return int(abs(float(s)))
    except (TypeError, ValueError):
        return None


def _row_matches_rule(row: pd.Series, rule: dict) -> bool:
    """1つの仕訳帳行が1つのルールにマッチするか判定する。"""
    # 完全一致条件（勘定科目・補助科目）
    for key in _EXACT_KEYS:
        if key in rule and str(row.get(key, "")).strip() != str(rule[key]).strip():
            return False

    # 金額条件（整数完全一致）
    for rule_key, journal_col in _AMOUNT_KEYS.items():
        if rule_key in rule:
            row_amount = _normalize_amount(row.get(journal_col, ""))
            if row_amount != int(rule[rule_key]):
                return False

    # 摘要正規表現
    if _REGEX_KEY in rule:
        pattern = rule[_REGEX_KEY]
        text = str(row.get("摘要", ""))
        if not re.search(pattern, text):
            return False

    return True


def auto_clear(journal: pd.DataFrame, rules: list[dict]) -> AutoClearResult:
    """仕訳帳行のうちルールにマッチするものを消化対象として返す。

    複数ルールがある場合、いずれかにマッチした時点でその行を消化する
    （ルールは上から評価し、最初にマッチしたルール名が「適用ルール」に入る）。
    """
    if journal.empty or not rules:
        return AutoClearResult()

    matched_rows: list[dict] = []
    consumed: set[str] = set()

    for _, row in journal.iterrows():
        for rule in rules:
            if _row_matches_rule(row, rule):
                row_dict = row.to_dict()
                row_dict["適用ルール"] = rule.get("name", "")
                matched_rows.append(row_dict)
                consumed.add(str(row.get("取引No", "")))
                break  # 最初にヒットしたルールで決定

    cleared_df = pd.DataFrame(matched_rows) if matched_rows else pd.DataFrame()
    return AutoClearResult(cleared=cleared_df, consumed_journal_nos=consumed)
