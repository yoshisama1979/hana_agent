import re
import unicodedata

# ルール未登録時のデフォルト値。
# 仕訳帳側で freee が VISA デビ取込時に勘定科目未確定として入れる「★要確認」と
# 区別するため、classifier 由来は「★ルール未登録」を使う。
_UNREGISTERED_ACCOUNT = "★ルール未登録"
_UNCONFIRMED = {"入力名": "", "勘定科目": _UNREGISTERED_ACCOUNT, "補助科目": "", "税区分": ""}


def _normalize(text: str) -> str:
    """全角→半角（NFKC）正規化して大文字に変換する。"""
    return unicodedata.normalize("NFKC", text).upper()


def classify(merchant: str, rules: list[dict]) -> dict:
    """利用内容をルールリストと照合し、勘定科目情報を返す。
    マッチしない場合は ★ルール未登録 を返す。
    """
    normalized = _normalize(merchant)
    for rule in rules:
        pattern = _normalize(rule["match"])
        if re.search(pattern, normalized):
            return {
                "入力名": rule.get("入力名", ""),
                "勘定科目": rule.get("勘定科目", _UNREGISTERED_ACCOUNT),
                "補助科目": rule.get("補助科目", ""),
                "税区分": rule.get("税区分", ""),
            }
    return dict(_UNCONFIRMED)
