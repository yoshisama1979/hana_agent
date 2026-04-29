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


# ---------------------------------------------------------------------------
# M1: date_tolerance_days のデフォルトは0で、後方互換（既存挙動と一致）
# 厳格一致のみで段階拡張は行われない。
# ---------------------------------------------------------------------------
def test_match_default_tolerance_zero_keeps_strict_behavior():
    debit = _risona([
        {"利用日": "2025年04月07日", "利用内容": "ZOOM", "金額": "4968"},
        {"利用日": "2025年04月15日", "利用内容": "APPLE", "金額": "1680"},
    ])
    journal = _journal([
        {"取引日": "2025/04/07", "借方金額(円)": "4968", "摘要": "ZOOM"},
        {"取引日": "2025/04/16", "借方金額(円)": "1680", "摘要": "APPLE"},  # 1日ズレ
    ])

    result = match(debit, journal)

    # 厳格一致（4/7 ZOOM のみ）。APPLEは未マッチ。
    assert len(result.matched) == 1
    assert len(result.debit_only) == 1
    assert len(result.journal_only) == 1


# ---------------------------------------------------------------------------
# M2: date_tolerance_days=1 で日付ズレ1日の同金額がマッチする
# ---------------------------------------------------------------------------
def test_match_with_tolerance_one_pairs_one_day_off():
    debit = pd.DataFrame([
        {"お取引日": "2025/04/15", "お取引内容": "APPLE", "お取引金額": "1680"},
    ])
    journal = _journal([
        {"取引日": "2025/04/16", "借方金額(円)": "1680", "摘要": "APPLE"},
    ])

    result = match(
        debit, journal,
        debit_date_col="お取引日",
        debit_amount_col="お取引金額",
        date_tolerance_days=1,
    )

    assert len(result.matched) == 1
    assert result.matched.iloc[0]["照合方法"] == "日付ズレ"
    assert int(result.matched.iloc[0]["日付ズレ日数"]) == 1


# ---------------------------------------------------------------------------
# M3: 厳格一致で消化された行は段階1以降の対象外
# 同金額に厳格一致候補とズレ候補が両方ある場合、厳格一致が優先消化される
# ---------------------------------------------------------------------------
def test_match_prefers_exact_match_over_date_offset():
    debit = pd.DataFrame([
        {"お取引日": "2025/04/15", "お取引内容": "APPLE A", "お取引金額": "1680"},
        {"お取引日": "2025/04/20", "お取引内容": "APPLE B", "お取引金額": "1680"},
    ])
    journal = _journal([
        {"取引日": "2025/04/15", "借方金額(円)": "1680", "摘要": "厳格一致"},
        {"取引日": "2025/04/21", "借方金額(円)": "1680", "摘要": "1日ズレ"},
    ])

    result = match(
        debit, journal,
        debit_date_col="お取引日",
        debit_amount_col="お取引金額",
        date_tolerance_days=1,
    )

    # 4/15 同士は厳格一致。4/20 と 4/21 は1日ズレでマッチ。
    assert len(result.matched) == 2
    # 厳格一致行を取り出す
    exact = result.matched[result.matched["照合方法"] == "完全一致"]
    fuzzy = result.matched[result.matched["照合方法"] == "日付ズレ"]
    assert len(exact) == 1
    assert len(fuzzy) == 1
    # 厳格一致は 4/15 同士
    assert exact.iloc[0]["お取引日"] == "2025/04/15"
    assert exact.iloc[0]["取引日"] == "2025/04/15"


# ---------------------------------------------------------------------------
# M4: 完全一致行に「照合方法=完全一致」「日付ズレ日数=0」が付く
# ---------------------------------------------------------------------------
def test_match_tags_exact_pairs_with_zero_offset():
    debit = _risona([{"利用日": "2025年04月07日", "利用内容": "ZOOM", "金額": "4968"}])
    journal = _journal([
        {"取引日": "2025/04/07", "借方金額(円)": "4968", "摘要": "VISAデビ"}
    ])

    result = match(debit, journal, date_tolerance_days=7)

    assert len(result.matched) == 1
    assert result.matched.iloc[0]["照合方法"] == "完全一致"
    assert int(result.matched.iloc[0]["日付ズレ日数"]) == 0


# ---------------------------------------------------------------------------
# M5: 段階N=2 で +2日, -2日 双方向のズレが拾える
# ---------------------------------------------------------------------------
def test_match_with_tolerance_pairs_both_directions():
    debit = pd.DataFrame([
        {"お取引日": "2025/04/10", "お取引内容": "FORWARD", "お取引金額": "1000"},
        {"お取引日": "2025/04/20", "お取引内容": "BACKWARD", "お取引金額": "2000"},
    ])
    journal = _journal([
        {"取引日": "2025/04/12", "借方金額(円)": "1000", "摘要": "+2日"},
        {"取引日": "2025/04/18", "借方金額(円)": "2000", "摘要": "-2日"},
    ])

    result = match(
        debit, journal,
        debit_date_col="お取引日",
        debit_amount_col="お取引金額",
        date_tolerance_days=2,
    )

    assert len(result.matched) == 2
    assert (result.matched["照合方法"] == "日付ズレ").all()
    assert set(result.matched["日付ズレ日数"].astype(int)) == {2}


# ---------------------------------------------------------------------------
# M6: 段階1 内で複数候補がある場合 greedy に1:1で消化
# ---------------------------------------------------------------------------
def test_match_greedy_pairing_within_stage():
    debit = pd.DataFrame([
        {"お取引日": "2025/04/15", "お取引内容": "A", "お取引金額": "1000"},
        {"お取引日": "2025/04/15", "お取引内容": "B", "お取引金額": "1000"},
    ])
    journal = _journal([
        {"取引日": "2025/04/16", "借方金額(円)": "1000", "摘要": "X"},
        {"取引日": "2025/04/16", "借方金額(円)": "1000", "摘要": "Y"},
    ])

    result = match(
        debit, journal,
        debit_date_col="お取引日",
        debit_amount_col="お取引金額",
        date_tolerance_days=1,
    )

    # 2件 × 2件 → 2ペア成立
    assert len(result.matched) == 2
    assert len(result.debit_only) == 0
    assert len(result.journal_only) == 0
    assert (result.matched["日付ズレ日数"].astype(int) == 1).all()


# ---------------------------------------------------------------------------
# M7: 許容範囲を超えるズレは未マッチのまま残る
# ---------------------------------------------------------------------------
def test_match_keeps_unmatched_beyond_tolerance():
    debit = pd.DataFrame([
        {"お取引日": "2025/04/01", "お取引内容": "FAR", "お取引金額": "5000"},
    ])
    journal = _journal([
        {"取引日": "2025/04/15", "借方金額(円)": "5000", "摘要": "14日離れ"},
    ])

    result = match(
        debit, journal,
        debit_date_col="お取引日",
        debit_amount_col="お取引金額",
        date_tolerance_days=7,
    )

    assert len(result.matched) == 0
    assert len(result.debit_only) == 1
    assert len(result.journal_only) == 1


# ---------------------------------------------------------------------------
# M-A1: offsets=[0] 指定で段階0のみ実行され、段階1以降は処理されない
# ---------------------------------------------------------------------------
def test_match_with_offsets_zero_only_skips_higher_stages():
    debit = pd.DataFrame([
        {"お取引日": "2025/04/15", "お取引内容": "ONE_DAY_OFF", "お取引金額": "1000"},
    ])
    journal = _journal([
        {"取引日": "2025/04/16", "借方金額(円)": "1000", "摘要": "1日違い"},
    ])

    result = match(
        debit, journal,
        debit_date_col="お取引日",
        debit_amount_col="お取引金額",
        offsets=[0],
    )

    # offset=0 のみ → 1日違いはマッチしない
    assert len(result.matched) == 0
    assert len(result.debit_only) == 1


# ---------------------------------------------------------------------------
# M-A2: offsets=[2] 指定で段階2のみ実行され、段階0/1 は処理されない
# ---------------------------------------------------------------------------
def test_match_with_offsets_specific_value_runs_only_that_stage():
    debit = pd.DataFrame([
        {"お取引日": "2025/04/15", "お取引内容": "EXACT", "お取引金額": "1000"},
        {"お取引日": "2025/04/15", "お取引内容": "TWO_DAY_OFF", "お取引金額": "2000"},
    ])
    journal = _journal([
        {"取引日": "2025/04/15", "借方金額(円)": "1000", "摘要": "完全一致"},
        {"取引日": "2025/04/17", "借方金額(円)": "2000", "摘要": "2日違い"},
    ])

    result = match(
        debit, journal,
        debit_date_col="お取引日",
        debit_amount_col="お取引金額",
        offsets=[2],
    )

    # offset=2 のみ → 完全一致は無視され、2日違いのみマッチ
    assert len(result.matched) == 1
    assert int(result.matched.iloc[0]["日付ズレ日数"]) == 2
    assert len(result.debit_only) == 1  # EXACT が残る


# ---------------------------------------------------------------------------
# M-A3: offsets 未指定なら従来通り range(date_tolerance_days+1) を使う（後方互換）
# ---------------------------------------------------------------------------
def test_match_without_offsets_uses_date_tolerance_days_default():
    debit = pd.DataFrame([
        {"お取引日": "2025/04/15", "お取引内容": "EXACT", "お取引金額": "1000"},
        {"お取引日": "2025/04/15", "お取引内容": "ONE_DAY_OFF", "お取引金額": "2000"},
    ])
    journal = _journal([
        {"取引日": "2025/04/15", "借方金額(円)": "1000", "摘要": "完全一致"},
        {"取引日": "2025/04/16", "借方金額(円)": "2000", "摘要": "1日違い"},
    ])

    result = match(
        debit, journal,
        debit_date_col="お取引日",
        debit_amount_col="お取引金額",
        date_tolerance_days=1,
    )

    assert len(result.matched) == 2
