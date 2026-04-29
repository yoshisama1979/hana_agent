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
    # 利用日と引落日のズレを吸収するため、SBIは±14日まで段階的に許容する
    # （エフィールウォーター等で実際に約9〜11日ズレるケースがある）
    assert sbi.date_tolerance_days == 14
    # 海外通貨取引は仕訳帳側で「本体+手数料」の合算金額で1行に計上されるため
    assert sbi.fee_cols == ("海外事務手数料",)


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
    # りそなは現状ズレ吸収不要なので 0（厳格一致のみ）
    assert risona.date_tolerance_days == 0
    # りそなは海外取引時の手数料合算がない想定
    assert risona.fee_cols == ()
    # 通常CSVなので header_marker/footer_marker は None
    assert risona.header_marker is None
    assert risona.footer_marker is None


# ---------------------------------------------------------------------------
# Q: ライフカードプロファイルが card_id="lifecard"、必要属性を持つ
# ---------------------------------------------------------------------------
def test_lifecard_profile_is_defined():
    lifecard = PROFILES["lifecard"]
    assert lifecard.card_id == "lifecard"
    assert lifecard.account_name == "ミライノ カード(MasterCard)ミライノカード Bu"
    assert lifecard.date_col == "利用日"
    assert lifecard.amount_col == "利用金額"
    assert lifecard.merchant_col == "利用先"
    assert lifecard.has_status is False
    # 同日マッチが大半なのでズレ許容は0
    assert lifecard.date_tolerance_days == 0
    # 海外手数料カラムは使わない（明細上の手数料は0件）
    assert lifecard.fee_cols == ()
    # 冒頭19行のメタ情報を読み飛ばすマーカ
    assert lifecard.header_marker == "明細No."
    assert lifecard.footer_marker == "回数指定払"


# ---------------------------------------------------------------------------
# A-3: date_tolerance_days のデフォルト値は 0（後方互換）
# ---------------------------------------------------------------------------
def test_card_profile_date_tolerance_default_is_zero():
    profile = CardProfile(
        card_id="dummy",
        account_name="dummy",
        date_col="利用日",
        amount_col="金額",
        merchant_col="利用内容",
        has_status=False,
        debit_pattern="dummy",
    )
    assert profile.date_tolerance_days == 0


# ---------------------------------------------------------------------------
# A-5: header_marker / footer_marker のデフォルトは None（後方互換）
# ---------------------------------------------------------------------------
def test_card_profile_marker_defaults_are_none():
    profile = CardProfile(
        card_id="dummy",
        account_name="dummy",
        date_col="利用日",
        amount_col="金額",
        merchant_col="利用内容",
        has_status=False,
        debit_pattern="dummy",
    )
    assert profile.header_marker is None
    assert profile.footer_marker is None


# ---------------------------------------------------------------------------
# L-1: header_marker 指定時、そこから始まる行を CSV ヘッダーとして読む
# 冒頭のメタ情報行（支払日や会員氏名）はスキップされる
# ---------------------------------------------------------------------------
def test_load_debit_skips_pre_header_meta_when_marker_set(tmp_path):
    csv = tmp_path / "lifecard_meisai.csv"
    csv.write_text(
        "支払日,2025年04月28日\n"
        "会員氏名,テスト 太郎\n"
        "\n"
        "明細No.,利用日,利用先,利用金額\n"
        '"0001","2025/03/29","TEST SHOP","3455"\n',
        encoding="cp932",
    )
    profile = CardProfile(
        card_id="dummy",
        account_name="dummy",
        date_col="利用日",
        amount_col="利用金額",
        merchant_col="利用先",
        has_status=False,
        debit_pattern=str(csv),
        header_marker="明細No.",
    )

    df = profile.load_debit()

    assert len(df) == 1
    assert list(df.columns) == ["明細No.", "利用日", "利用先", "利用金額"]
    assert df.iloc[0]["利用先"] == "TEST SHOP"


# ---------------------------------------------------------------------------
# L-2: footer_marker 指定時、その行以降は無視される
# ---------------------------------------------------------------------------
def test_load_debit_truncates_at_footer_marker(tmp_path):
    csv = tmp_path / "lifecard_meisai.csv"
    csv.write_text(
        "明細No.,利用日,利用先,利用金額\n"
        '"0001","2025/03/29","SHOP A","1000"\n'
        '"0002","2025/03/30","SHOP B","2000"\n'
        "\n"
        "回数指定払 内訳表\n"
        "明細No.,お支払総額,ご利用金額\n"
        '"0001","1000","1000"\n',
        encoding="cp932",
    )
    profile = CardProfile(
        card_id="dummy",
        account_name="dummy",
        date_col="利用日",
        amount_col="利用金額",
        merchant_col="利用先",
        has_status=False,
        debit_pattern=str(csv),
        header_marker="明細No.",
        footer_marker="回数指定払",
    )

    df = profile.load_debit()

    # フッター内訳表は除外される
    assert len(df) == 2
    assert set(df["利用先"]) == {"SHOP A", "SHOP B"}


# ---------------------------------------------------------------------------
# L-3: header_marker が見つからない場合は ValueError
# ---------------------------------------------------------------------------
def test_load_debit_raises_when_header_marker_missing(tmp_path):
    csv = tmp_path / "lifecard_meisai.csv"
    csv.write_text(
        "支払日,2025年04月28日\n"
        "会員氏名,テスト 太郎\n",
        encoding="cp932",
    )
    profile = CardProfile(
        card_id="dummy",
        account_name="dummy",
        date_col="利用日",
        amount_col="利用金額",
        merchant_col="利用先",
        has_status=False,
        debit_pattern=str(csv),
        header_marker="明細No.",
    )

    import pytest as _pytest
    with _pytest.raises(ValueError, match="明細No\\."):
        profile.load_debit()


# ---------------------------------------------------------------------------
# A-4: fee_cols のデフォルトは空タプル（後方互換）
# ---------------------------------------------------------------------------
def test_card_profile_fee_cols_default_is_empty():
    profile = CardProfile(
        card_id="dummy",
        account_name="dummy",
        date_col="利用日",
        amount_col="金額",
        merchant_col="利用内容",
        has_status=False,
        debit_pattern="dummy",
    )
    assert profile.fee_cols == ()


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
