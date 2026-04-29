import pandas as pd

from accounting.matcher import match


def _risona(rows: list[dict]) -> pd.DataFrame:
    """りそな明細の最小DataFrameを生成するヘルパー。"""
    return pd.DataFrame(rows)


def _journal(rows: list[dict]) -> pd.DataFrame:
    """仕訳帳の最小DataFrameを生成するヘルパー。"""
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# S1: 金額と日付が完全一致する行を照合済みとして分類する
# ---------------------------------------------------------------------------
def test_match_returns_matched_when_amount_and_date_match():
    # Given
    risona = _risona([{"利用日": "2025年04月07日", "利用内容": "ZOOM.COM", "金額": "4968"}])
    journal = _journal([
        {"取引日": "2025/04/07", "借方金額(円)": "4968", "摘要": "VISAデビ 0123456A"}
    ])

    # When
    result = match(risona, journal)

    # Then
    assert len(result.matched) == 1
    assert len(result.debit_only) == 0
    assert len(result.journal_only) == 0


# ---------------------------------------------------------------------------
# S2: 同日・同金額が複数あるが件数一致 → matched に入り要目視フラグが立つ
# ---------------------------------------------------------------------------
def test_match_returns_matched_with_review_flag_when_same_date_amount_n_to_n():
    # Given
    risona = _risona([
        {"利用日": "2025年04月07日", "利用内容": "SHOPА", "金額": "1000"},
        {"利用日": "2025年04月07日", "利用内容": "SHOPB", "金額": "1000"},
    ])
    journal = _journal([
        {"取引日": "2025/04/07", "借方金額(円)": "1000", "摘要": "VISAデビ 0000001A"},
        {"取引日": "2025/04/07", "借方金額(円)": "1000", "摘要": "VISAデビ 0000002A"},
    ])

    # When
    result = match(risona, journal)

    # Then
    assert len(result.matched) == 2
    assert (result.matched["要目視確認"] == "要確認").all()
    assert len(result.duplicates) == 0


# ---------------------------------------------------------------------------
# S2b: 同日・同金額だが件数不一致 → duplicates＋余剰は未照合
# ---------------------------------------------------------------------------
def test_match_returns_duplicates_when_counts_differ():
    # Given
    risona = _risona([
        {"利用日": "2025年04月07日", "利用内容": "SHOPА", "金額": "1000"},
        {"利用日": "2025年04月07日", "利用内容": "SHOPB", "金額": "1000"},
    ])
    journal = _journal([
        {"取引日": "2025/04/07", "借方金額(円)": "1000", "摘要": "VISAデビ 0000001A"},
    ])

    # When
    result = match(risona, journal)

    # Then
    assert len(result.duplicates) == 1
    assert len(result.debit_only) == 1


# ---------------------------------------------------------------------------
# S3: りそなのみに存在する行を未照合として分類する
# ---------------------------------------------------------------------------
def test_match_returns_risona_only_when_no_journal_entry():
    # Given
    risona = _risona([{"利用日": "2025年05月01日", "利用内容": "AWS", "金額": "10000"}])
    journal = _journal([
        {"取引日": "2025/04/07", "借方金額(円)": "4968", "摘要": "VISAデビ 0123456A"}
    ])

    # When
    result = match(risona, journal)

    # Then
    assert len(result.debit_only) == 1
    assert len(result.matched) == 0


# ---------------------------------------------------------------------------
# S4: 仕訳帳のみに存在する行を未照合として分類する
# ---------------------------------------------------------------------------
def test_match_returns_journal_only_when_no_risona_entry():
    # Given
    risona = _risona([{"利用日": "2025年04月07日", "利用内容": "ZOOM.COM", "金額": "4968"}])
    journal = _journal([
        {"取引日": "2025/04/07", "借方金額(円)": "4968", "摘要": "VISAデビ 0123456A"},
        {"取引日": "2025/05/01", "借方金額(円)": "10000", "摘要": "VISAデビ 0999999A"},
    ])

    # When
    result = match(risona, journal)

    # Then
    assert len(result.journal_only) == 1
    assert len(result.matched) == 1


# ---------------------------------------------------------------------------
# S5: りそな金額がマイナス（返金）でも仕訳帳の正値と絶対値で照合する
# ---------------------------------------------------------------------------
def test_match_pairs_negative_risona_amount_with_positive_journal_amount():
    # Given: りそなは返金で-83824、仕訳帳は借方/貸方で方向を表現し金額は正値
    risona = _risona([
        {"利用日": "2025年10月22日", "利用内容": "CROWDWORKS", "金額": "-83824"}
    ])
    journal = _journal([
        {"取引日": "2025/10/22", "借方金額(円)": "83824", "摘要": "VISAデビ 0857360A"}
    ])

    # When
    result = match(risona, journal)

    # Then
    assert len(result.matched) == 1
    assert len(result.debit_only) == 0
    assert len(result.journal_only) == 0


# ---------------------------------------------------------------------------
# S6: 金額にカンマが含まれていても整数として比較する
# ---------------------------------------------------------------------------
def test_match_handles_comma_separated_amount():
    # Given: 仕訳帳側にカンマ区切りの金額が入る場合
    risona = _risona([{"利用日": "2025年04月07日", "利用内容": "ZOOM", "金額": "4968"}])
    journal = _journal([
        {"取引日": "2025/04/07", "借方金額(円)": "4,968", "摘要": "VISAデビ 0000001A"}
    ])

    # When
    result = match(risona, journal)

    # Then
    assert len(result.matched) == 1


# ---------------------------------------------------------------------------
# S7: 明細側のカラム名を引数で指定すると、SBIのような別カラム構成でも照合できる
# ---------------------------------------------------------------------------
def test_match_accepts_custom_debit_columns_for_sbi():
    # Given: SBIは「お取引日」「お取引金額」、金額は小数文字列
    debit = pd.DataFrame([
        {"お取引日": "2025/04/29", "お取引内容": "APPLE COM BILL", "お取引金額": "400.00"}
    ])
    journal = _journal([
        {"取引日": "2025/04/29", "借方金額(円)": "400", "摘要": "VISAデビ APPLE"}
    ])

    # When
    result = match(
        debit, journal,
        debit_date_col="お取引日",
        debit_amount_col="お取引金額",
    )

    # Then
    assert len(result.matched) == 1
    assert len(result.debit_only) == 0
    assert len(result.journal_only) == 0


# ---------------------------------------------------------------------------
# S8: 明細側のマイナス小数（返金）も絶対値で照合される
# ---------------------------------------------------------------------------
def test_match_handles_negative_decimal_amount():
    debit = pd.DataFrame([
        {"お取引日": "2025/05/10", "お取引内容": "REFUND", "お取引金額": "-1500.00"}
    ])
    journal = _journal([
        {"取引日": "2025/05/10", "借方金額(円)": "1500", "摘要": "返金"}
    ])

    result = match(
        debit, journal,
        debit_date_col="お取引日",
        debit_amount_col="お取引金額",
    )

    assert len(result.matched) == 1
