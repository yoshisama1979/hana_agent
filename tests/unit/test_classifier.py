
from accounting.classifier import classify

RULES = [
    {"match": "ZOOM", "勘定科目": "消耗品費", "補助科目": "Zoom", "税区分": "課税仕入"},
    {"match": "ADOBE|アドビ", "勘定科目": "消耗品費", "補助科目": "Adobe", "税区分": "課税仕入"},
]


# ---------------------------------------------------------------------------
# S5: ルールにマッチする利用内容に勘定科目を付与する
# ---------------------------------------------------------------------------
def test_classify_returns_account_when_rule_matches():
    # Given
    merchant = "ZOOM.COM 888-799-9666"

    # When
    result = classify(merchant, RULES)

    # Then
    assert result["勘定科目"] == "消耗品費"
    assert result["補助科目"] == "Zoom"


# ---------------------------------------------------------------------------
# S6: 全角表記でもルールにマッチする
# ---------------------------------------------------------------------------
def test_classify_matches_fullwidth_text_via_normalization():
    # Given
    merchant = "アドビカブシキガイシャ"

    # When
    result = classify(merchant, RULES)

    # Then
    assert result["勘定科目"] == "消耗品費"


# ---------------------------------------------------------------------------
# S7: どのルールにもマッチしない場合は★要確認とする
# ---------------------------------------------------------------------------
def test_classify_returns_unconfirmed_when_no_rule_matches():
    # Given
    merchant = "UNKNOWN SHOP"

    # When
    result = classify(merchant, RULES)

    # Then
    assert result["勘定科目"] == "★要確認"
