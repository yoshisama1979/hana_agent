"""
card_profiles の単体テスト

各カードプロファイルが仕様通りに定義されているか、明細CSVの読み込みが
複数ファイルの結合・重複除外を正しく行うかを確認する。
"""

import pandas as pd
import pytest

from accounting.card_profiles import PROFILES, CardProfile


# ---------------------------------------------------------------------------
# A-1: SBIプロファイルが card_id="sbi"、口座名と必要属性を持つ
# ---------------------------------------------------------------------------
def test_sbi_profile_is_defined():
    sbi = PROFILES["sbi"]
    assert sbi.card_id == "sbi"
    assert sbi.account_name == "住信SBI106代表口座 - 円普通2212165"
    assert sbi.date_col == "お取引日"
    assert sbi.amount_col == "お取引金額"
    assert sbi.merchant_col == "お取引内容"
    assert sbi.has_status is False


# ---------------------------------------------------------------------------
# A-2: りそなプロファイルが card_id="risona"、口座名と必要属性を持つ
# ---------------------------------------------------------------------------
def test_risona_profile_is_defined():
    risona = PROFILES["risona"]
    assert risona.card_id == "risona"
    assert risona.account_name == "りそな銀行大手支店普通0073514"
    assert risona.date_col == "利用日"
    assert risona.amount_col == "金額"
    assert risona.merchant_col == "利用内容"
    assert risona.has_status is True


# ---------------------------------------------------------------------------
# B-1: 複数CSVを glob で読み込み、結合した DataFrame を返す
# ---------------------------------------------------------------------------
def test_load_debit_reads_and_concats_multiple_files(tmp_path):
    file_a = tmp_path / "meisai_a.csv"
    file_b = tmp_path / "meisai_b.csv"
    file_a.write_text(
        '"1","お取引日","お取引内容","お取引金額"\n'
        '"2","2025/04/01","SHOP A","1000"\n',
        encoding="cp932",
    )
    file_b.write_text(
        '"1","お取引日","お取引内容","お取引金額"\n'
        '"2","2025/05/01","SHOP B","2000"\n',
        encoding="cp932",
    )
    profile = CardProfile(
        card_id="dummy",
        account_name="dummy",
        date_col="お取引日",
        amount_col="お取引金額",
        merchant_col="お取引内容",
        has_status=False,
        debit_pattern=str(tmp_path / "meisai_*.csv"),
    )

    df = profile.load_debit()

    assert len(df) == 2
    assert set(df["お取引内容"]) == {"SHOP A", "SHOP B"}


# ---------------------------------------------------------------------------
# B-2: 取引日 × 利用内容 × 金額 が一致する重複行は除外する
# ---------------------------------------------------------------------------
def test_load_debit_drops_duplicates_across_files(tmp_path):
    file_a = tmp_path / "meisai_a.csv"
    file_b = tmp_path / "meisai_b.csv"
    common_row = '"2","2025/04/30","SHOP X","500"\n'
    file_a.write_text(
        '"1","お取引日","お取引内容","お取引金額"\n'
        + common_row,
        encoding="cp932",
    )
    file_b.write_text(
        '"1","お取引日","お取引内容","お取引金額"\n'
        + common_row,
        encoding="cp932",
    )
    profile = CardProfile(
        card_id="dummy",
        account_name="dummy",
        date_col="お取引日",
        amount_col="お取引金額",
        merchant_col="お取引内容",
        has_status=False,
        debit_pattern=str(tmp_path / "meisai_*.csv"),
    )

    df = profile.load_debit()

    assert len(df) == 1


# ---------------------------------------------------------------------------
# B-3: glob でファイルが1件もマッチしない場合は FileNotFoundError
# ---------------------------------------------------------------------------
def test_load_debit_raises_when_no_files_match(tmp_path):
    profile = CardProfile(
        card_id="dummy",
        account_name="dummy",
        date_col="お取引日",
        amount_col="お取引金額",
        merchant_col="お取引内容",
        has_status=False,
        debit_pattern=str(tmp_path / "missing_*.csv"),
    )

    with pytest.raises(FileNotFoundError):
        profile.load_debit()


# ---------------------------------------------------------------------------
# 単一ファイル時は重複除外をかけない（同日同店舗で2回利用などを保持）
# ---------------------------------------------------------------------------
def test_load_debit_keeps_duplicates_within_single_file(tmp_path):
    csv = tmp_path / "risona.csv"
    csv.write_text(
        '"利用日","利用内容","金額","ステータス"\n'
        '"2025年04月07日","COFFEE SHOP","320","確定"\n'
        '"2025年04月07日","COFFEE SHOP","320","確定"\n',
        encoding="cp932",
    )
    profile = CardProfile(
        card_id="dummy",
        account_name="dummy",
        date_col="利用日",
        amount_col="金額",
        merchant_col="利用内容",
        has_status=True,
        debit_pattern=str(csv),
    )

    df = profile.load_debit()

    assert len(df) == 2


# ---------------------------------------------------------------------------
# 単一ファイル指定（りそなのように glob でない literal pathでも動く）
# ---------------------------------------------------------------------------
def test_load_debit_reads_single_file(tmp_path):
    csv = tmp_path / "risona.csv"
    csv.write_text(
        '"利用日","利用内容","金額","ステータス"\n'
        '"2025年04月07日","ZOOM","4968","確定"\n',
        encoding="cp932",
    )
    profile = CardProfile(
        card_id="dummy",
        account_name="dummy",
        date_col="利用日",
        amount_col="金額",
        merchant_col="利用内容",
        has_status=True,
        debit_pattern=str(csv),
    )

    df = profile.load_debit()

    assert len(df) == 1
    assert df.iloc[0]["利用内容"] == "ZOOM"
