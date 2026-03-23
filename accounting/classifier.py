import re
import unicodedata

_UNCONFIRMED = {"勘定科目": "★要確認", "補助科目": "", "税区分": ""}


def _normalize(text: str) -> str:
    """全角→半角（NFKC）正規化して大文字に変換する。"""
    return unicodedata.normalize("NFKC", text).upper()


def classify(merchant: str, rules: list[dict]) -> dict:
    """利用内容をルールリストと照合し、勘定科目情報を返す。
    マッチしない場合は ★要確認 を返す。
    """
    normalized = _normalize(merchant)
    for rule in rules:
        pattern = _normalize(rule["match"])
        if re.search(pattern, normalized):
            return {
                "勘定科目": rule.get("勘定科目", "★要確認"),
                "補助科目": rule.get("補助科目", ""),
                "税区分": rule.get("税区分", ""),
            }
    return dict(_UNCONFIRMED)
