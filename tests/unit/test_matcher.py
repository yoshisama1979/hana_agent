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
    assert len(result.risona_only) == 0
    assert len(result.journal_only) == 0


# ---------------------------------------------------------------------------
# S2: 同日・同金額が複数ある行を重複として分類する
# ---------------------------------------------------------------------------
def test_match_returns_duplicates_when_same_date_amount_appears_multiple_times():
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
    assert len(result.duplicates) == 2
    assert len(result.matched) == 0


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
    assert len(result.risona_only) == 1
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
