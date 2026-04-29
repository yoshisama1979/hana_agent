"""
reconcile.run() の結合テスト

両カード（りそな・SBI）の照合を一気に走らせ、
- 出力サブディレクトリ構成
- 仕訳帳のみ.csv の集約
- ステータス無しカード（SBI）で未確定/対象外CSVが出力されないこと
を確認する。
"""

from pathlib import Path

import pandas as pd
import pytest

from accounting.card_profiles import CardProfile
from accounting.reconcile import run

RISONA_ACCOUNT = "りそな銀行大手支店普通0073514"
SBI_ACCOUNT = "住信SBI106代表口座 - 円普通2212165"


def _write_journal(path: Path) -> None:
    """両カードを含む小さな仕訳帳CSVを作成"""
    df = pd.DataFrame([
        # りそな - 照合可能
        {"取引No": "1", "取引日": "2025/04/07",
         "借方勘定科目": "通信費", "借方補助科目": "", "借方金額(円)": "4968",
         "貸方勘定科目": "普通預金", "貸方補助科目": RISONA_ACCOUNT, "貸方金額(円)": "4968",
         "摘要": "VISAデビ ZOOM"},
        # りそな - 普通預金との振替なので照合対象外（出力には残る）
        {"取引No": "2", "取引日": "2025/04/10",
         "借方勘定科目": "普通預金", "借方補助科目": "別口座", "借方金額(円)": "100000",
         "貸方勘定科目": "普通預金", "貸方補助科目": RISONA_ACCOUNT, "貸方金額(円)": "100000",
         "摘要": "口座間振替"},
        # SBI - 照合可能
        {"取引No": "3", "取引日": "2025/04/29",
         "借方勘定科目": "消耗品費", "借方補助科目": "", "借方金額(円)": "400",
         "貸方勘定科目": "普通預金", "貸方補助科目": SBI_ACCOUNT, "貸方金額(円)": "400"},
        # 何のカードにも該当しない（仕訳帳のみ.csv に残る）
        {"取引No": "4", "取引日": "2025/04/15",
         "借方勘定科目": "租税公課", "借方補助科目": "", "借方金額(円)": "5000",
         "貸方勘定科目": "現金", "貸方補助科目": "", "貸方金額(円)": "5000",
         "摘要": "印紙"},
        # SBI - 海外通貨案件：仕訳帳側は本体+手数料の合算で計上されている
        # （明細では VERCEL 2881 + 海外事務手数料 72 = 2953）
        {"取引No": "5", "取引日": "2025/05/15",
         "借方勘定科目": "支払手数料", "借方補助科目": "", "借方金額(円)": "2953",
         "貸方勘定科目": "普通預金", "貸方補助科目": SBI_ACCOUNT, "貸方金額(円)": "2953",
         "摘要": "VERCEL INC."},
        # 売掛金照合 ペア（請求 → 入金）
        {"取引No": "6", "取引日": "2025/04/18",
         "借方勘定科目": "売掛金", "借方補助科目": "株式会社A", "借方金額(円)": "100000",
         "貸方勘定科目": "売上高", "貸方補助科目": "", "貸方金額(円)": "100000",
         "摘要": "請求4月分"},
        {"取引No": "7", "取引日": "2025/05/09",
         "借方勘定科目": "普通預金", "借方補助科目": SBI_ACCOUNT, "借方金額(円)": "100000",
         "貸方勘定科目": "売掛金", "貸方補助科目": "株式会社A", "貸方金額(円)": "100000",
         "摘要": "入金4月分"},
    ])
    # 不足カラムは空で埋める（実ファイルに合わせる）
    for col in ["借方部門", "借方取引先", "借方税区分", "借方インボイス",
                "貸方部門", "貸方取引先", "貸方税区分", "貸方インボイス",
                "タグ", "メモ"]:
        if col not in df.columns:
            df[col] = ""
    df.to_csv(path, index=False, encoding="cp932")


def _write_risona_debit(path: Path) -> None:
    df = pd.DataFrame([
        {"利用日": "2025年04月07日", "利用内容": "ZOOM.COM", "金額": "4968",
         "承認番号": "0123456A", "ステータス": "確定"},
        # 未確定（仕訳化前）
        {"利用日": "2025年04月20日", "利用内容": "PENDING SHOP", "金額": "1000",
         "承認番号": "0999999A", "ステータス": "未確定"},
        # 決済不可
        {"利用日": "2025年04月25日", "利用内容": "DECLINED SHOP", "金額": "2000",
         "承認番号": "0888888A", "ステータス": "決済不可"},
    ])
    df.to_csv(path, index=False, encoding="cp932")


def _write_sbi_meisai(dir_path: Path) -> None:
    """SBI明細を月別2ファイルに分けて作成（一部重複行を含む）"""
    common_cols = ["1", "お取引日", "お取引内容", "お取引通貨", "お取引金額",
                   "お取引手数料", "ATM手数料", "海外事務手数料", "ご利用通貨",
                   "ご利用金額", "ご利用手数料", "換算レート"]

    df_apr = pd.DataFrame([
        ["2", "2025/04/29", "APPLE COM BILL", "JPY", "400.00",
         "0.00", "0.00", "0.00", "", "0.00", "0.00", "0.00"],
    ], columns=common_cols)
    (dir_path / "meisai_apr.csv").write_text(
        df_apr.to_csv(index=False), encoding="cp932"
    )

    # may でも APPLE COM BILL が重複（実データの月またぎを再現）
    # VERCEL は本体2881 + 海外事務手数料72 で、仕訳帳側は2953で計上されている → パス2でマッチ
    df_may = pd.DataFrame([
        ["2", "2025/04/29", "APPLE COM BILL", "JPY", "400.00",
         "0.00", "0.00", "0.00", "", "0.00", "0.00", "0.00"],
        ["2", "2025/05/15", "VERCEL INC.", "JPY", "2881.00",
         "0.00", "0.00", "72.00", "USD", "20.00", "0.00", "144.05"],
    ], columns=common_cols)
    (dir_path / "meisai_may.csv").write_text(
        df_may.to_csv(index=False), encoding="cp932"
    )


def _write_rules(path: Path) -> None:
    path.write_text(
        "rules:\n"
        "  - match: \"ZOOM\"\n"
        "    入力名: Zoom\n"
        "    勘定科目: 通信費\n"
        "    補助科目: \"\"\n"
        "    税区分: 課税仕入\n",
        encoding="utf-8",
    )


@pytest.fixture
def setup_env(tmp_path):
    journal = tmp_path / "仕訳帳.csv"
    risona_debit = tmp_path / "risona_debit.csv"
    rules = tmp_path / "merchant_rules.yml"
    output_dir = tmp_path / "output"
    sbi_dir = tmp_path / "sbi_dir"
    sbi_dir.mkdir()

    _write_journal(journal)
    _write_risona_debit(risona_debit)
    _write_sbi_meisai(sbi_dir)
    _write_rules(rules)

    profiles = [
        CardProfile(
            card_id="risona",
            account_name=RISONA_ACCOUNT,
            date_col="利用日",
            amount_col="金額",
            merchant_col="利用内容",
            has_status=True,
            debit_pattern=str(risona_debit),
        ),
        CardProfile(
            card_id="sbi",
            account_name=SBI_ACCOUNT,
            date_col="お取引日",
            amount_col="お取引金額",
            merchant_col="お取引内容",
            has_status=False,
            debit_pattern=str(sbi_dir / "meisai_*.csv"),
            fee_cols=("海外事務手数料",),
        ),
    ]

    return {
        "profiles": profiles,
        "journal": journal,
        "rules": rules,
        "output": output_dir,
    }


# ---------------------------------------------------------------------------
# D-1, D-2: カードごとにサブディレクトリへ出力される
# ---------------------------------------------------------------------------
def test_run_writes_per_card_subdirectories(setup_env):
    run(**setup_env)

    assert (setup_env["output"] / "risona" / "カード_照合済み.csv").exists()
    assert (setup_env["output"] / "sbi" / "カード_照合済み.csv").exists()


# ---------------------------------------------------------------------------
# D-3: ステータス列のないSBIでは 未確定/対象外 CSV は出力されない
# ---------------------------------------------------------------------------
def test_run_skips_status_files_for_sbi(setup_env):
    run(**setup_env)

    assert not (setup_env["output"] / "sbi" / "カード_未確定.csv").exists()
    assert not (setup_env["output"] / "sbi" / "カード_対象外.csv").exists()
    # りそな側は両方出力される
    assert (setup_env["output"] / "risona" / "カード_未確定.csv").exists()
    assert (setup_env["output"] / "risona" / "カード_対象外.csv").exists()


# ---------------------------------------------------------------------------
# D-4: 仕訳帳のみ.csv は output 直下に1本、両カードの照合済みを除外
# ---------------------------------------------------------------------------
def test_run_writes_unified_journal_only_csv(setup_env):
    run(**setup_env)

    journal_only = setup_env["output"] / "仕訳帳のみ.csv"
    assert journal_only.exists()
    df = pd.read_csv(journal_only, encoding="utf-8-sig", dtype=str)

    nos = set(df["取引No"].astype(str))
    # 取引No 1 (りそな照合) と 3 (SBI照合) は除外されている
    assert "1" not in nos
    assert "3" not in nos
    # 取引No 2 (口座振替→カード照合スコープ外なので消化されない) と 4 は残る
    assert "2" in nos
    assert "4" in nos


# ---------------------------------------------------------------------------
# D-3 補足: SBIの照合済みは「お取引日」「お取引内容」のSBI由来カラムを保持
# ---------------------------------------------------------------------------
def test_sbi_matched_preserves_original_columns(setup_env):
    run(**setup_env)

    df = pd.read_csv(
        setup_env["output"] / "sbi" / "カード_照合済み.csv",
        encoding="utf-8-sig",
        dtype=str,
    )
    assert "お取引日" in df.columns
    assert "お取引内容" in df.columns
    assert "お取引金額" in df.columns


# ---------------------------------------------------------------------------
# B-2: SBIの月またぎ重複行が除外されたうえで照合される
# ---------------------------------------------------------------------------
def test_sbi_duplicate_rows_are_deduplicated(setup_env):
    run(**setup_env)

    df = pd.read_csv(
        setup_env["output"] / "sbi" / "カード_照合済み.csv",
        encoding="utf-8-sig",
        dtype=str,
    )
    # APPLE COM BILL は2ファイルに同一行で重複しているが1件にまとめる
    apple = df[df["お取引内容"] == "APPLE COM BILL"]
    assert len(apple) == 1


# ---------------------------------------------------------------------------
# R-1, R-3: パス1の行は金額種別=本体、パス2の行は金額種別=本体+手数料
# VERCEL（本体2881+手数料72=2953）は仕訳帳側で2953なのでパス2でマッチ
# ---------------------------------------------------------------------------
def test_sbi_fee_inclusive_match_tagged_correctly(setup_env):
    run(**setup_env)

    df = pd.read_csv(
        setup_env["output"] / "sbi" / "カード_照合済み.csv",
        encoding="utf-8-sig",
        dtype=str,
    )

    # APPLE COM BILL はパス1（金額そのまま）でマッチ
    apple = df[df["お取引内容"] == "APPLE COM BILL"].iloc[0]
    assert apple["金額種別"] == "本体"

    # VERCEL INC. はパス2（本体+手数料）でマッチ
    vercel = df[df["お取引内容"] == "VERCEL INC."].iloc[0]
    assert vercel["金額種別"] == "本体+手数料"


# ---------------------------------------------------------------------------
# R-5: fee_cols を持たないりそなはパス2を行わず、すべて 金額種別=本体
# ---------------------------------------------------------------------------
def test_risona_matched_rows_all_tagged_as_main(setup_env):
    run(**setup_env)

    df = pd.read_csv(
        setup_env["output"] / "risona" / "カード_照合済み.csv",
        encoding="utf-8-sig",
        dtype=str,
    )
    assert (df["金額種別"] == "本体").all()


# ---------------------------------------------------------------------------
# R-6: 仕訳帳のみ.csv からはパス1+パス2 両方の消化分が除外される
# 取引No 5（VERCEL）はパス2で消化されるので残らない
# ---------------------------------------------------------------------------
def test_journal_only_excludes_fee_inclusive_matches(setup_env):
    run(**setup_env)

    df = pd.read_csv(
        setup_env["output"] / "仕訳帳のみ.csv",
        encoding="utf-8-sig",
        dtype=str,
    )
    nos = set(df["取引No"].astype(str))
    assert "5" not in nos  # パス2で消化されているので残ってはいけない


# ---------------------------------------------------------------------------
# F-05: 売掛金照合の出力先と消化分の仕訳帳のみからの除外
# ---------------------------------------------------------------------------
def test_receivable_reconciliation_writes_pair_csv(setup_env):
    run(**setup_env)

    pair_csv = setup_env["output"] / "receivable" / "売掛金_照合済み.csv"
    assert pair_csv.exists()

    df = pd.read_csv(pair_csv, encoding="utf-8-sig", dtype=str)
    # 取引No 6（請求） と 7（入金） が1ペアになっている
    assert len(df) == 1
    pair = df.iloc[0]
    assert pair["請求_取引No"] == "6"
    assert pair["入金_取引No"] == "7"
    assert pair["補助科目"] == "株式会社A"


def test_receivable_consumed_rows_excluded_from_journal_only(setup_env):
    run(**setup_env)

    df = pd.read_csv(
        setup_env["output"] / "仕訳帳のみ.csv",
        encoding="utf-8-sig",
        dtype=str,
    )
    nos = set(df["取引No"].astype(str))
    # 売掛金照合で消化された請求・入金は仕訳帳のみから除外
    assert "6" not in nos
    assert "7" not in nos


# ---------------------------------------------------------------------------
# S-1（リグレッション）：日付近さ優先で、本体+手数料が大ズレ本体マッチに勝つ
#
# 想定シナリオ：
#   仕訳帳: 2026/01/28 金額3175 (VERCEL の本体+手数料3098+77=3175 が同日マッチすべき)
#   仕訳帳: 2026/01/17 金額3254 (CLAUDE.AI の本体+手数料3175+79=3254 が ±1日でマッチすべき)
#   明細  : VERCEL 2026/01/28 本体3098 + 手数料77 = 3175
#   明細  : CLAUDE.AI 2026/01/16 本体3175 + 手数料79 = 3254
#
# 旧ロジック（パス1全段階→パス2全段階）では CLAUDE.AI 本体3175 が
# 12日違いで仕訳帳3175を奪ってしまい、VERCEL が未入力に残る。
# 新ロジック（段階×戦略入れ子）では同日3175が VERCEL に正しくマッチする。
# ---------------------------------------------------------------------------
@pytest.fixture
def vercel_regression_env(tmp_path):
    journal = tmp_path / "仕訳帳.csv"
    rules = tmp_path / "rules.yml"
    output_dir = tmp_path / "output"
    sbi_dir = tmp_path / "sbi_dir"
    sbi_dir.mkdir()

    # 仕訳帳：VERCEL 同日3175、CLAUDE.AI ±1日3254
    journal_df = pd.DataFrame([
        {"取引No": "100", "取引日": "2026/01/28",
         "借方勘定科目": "★要確認", "借方補助科目": "", "借方金額(円)": "3175",
         "貸方勘定科目": "普通預金", "貸方補助科目": SBI_ACCOUNT, "貸方金額(円)": "3175",
         "摘要": "デビット 614771"},
        {"取引No": "101", "取引日": "2026/01/17",
         "借方勘定科目": "★要確認", "借方補助科目": "", "借方金額(円)": "3254",
         "貸方勘定科目": "普通預金", "貸方補助科目": SBI_ACCOUNT, "貸方金額(円)": "3254",
         "摘要": "デビット 974182"},
    ])
    for col in ["借方部門", "借方取引先", "借方税区分", "借方インボイス",
                "貸方部門", "貸方取引先", "貸方税区分", "貸方インボイス",
                "タグ", "メモ"]:
        if col not in journal_df.columns:
            journal_df[col] = ""
    journal_df.to_csv(journal, index=False, encoding="cp932")

    # SBI明細：VERCEL 2026/01/28、CLAUDE.AI 2026/01/16
    common_cols = ["1", "お取引日", "お取引内容", "お取引通貨", "お取引金額",
                   "お取引手数料", "ATM手数料", "海外事務手数料", "ご利用通貨",
                   "ご利用金額", "ご利用手数料", "換算レート"]
    sbi_df = pd.DataFrame([
        ["2", "2026/01/28", "VERCEL INC.", "JPY", "3098.00",
         "0.00", "0.00", "77.00", "USD", "20.00", "0.00", "154.90"],
        ["2", "2026/01/16", "CLAUDE.AI SUBSCRIPTION", "JPY", "3175.00",
         "0.00", "0.00", "79.00", "USD", "20.00", "0.00", "158.75"],
    ], columns=common_cols)
    (sbi_dir / "meisai.csv").write_text(sbi_df.to_csv(index=False), encoding="cp932")

    rules.write_text("rules: []\n", encoding="utf-8")

    profiles = [
        CardProfile(
            card_id="sbi",
            account_name=SBI_ACCOUNT,
            date_col="お取引日",
            amount_col="お取引金額",
            merchant_col="お取引内容",
            has_status=False,
            debit_pattern=str(sbi_dir / "meisai*.csv"),
            date_tolerance_days=14,
            fee_cols=("海外事務手数料",),
        ),
    ]
    return {
        "profiles": profiles,
        "journal": journal,
        "rules": rules,
        "output": output_dir,
    }


def test_date_proximity_priority_avoids_far_body_match_stealing_close_combined_match(
    vercel_regression_env,
):
    run(**vercel_regression_env)

    matched = pd.read_csv(
        vercel_regression_env["output"] / "sbi" / "カード_照合済み.csv",
        encoding="utf-8-sig",
        dtype=str,
    )
    debit_only = pd.read_csv(
        vercel_regression_env["output"] / "sbi" / "カード_未入力.csv",
        encoding="utf-8-sig",
        dtype=str,
    )

    # 両明細とも消化されていること
    assert len(debit_only) == 0
    assert len(matched) == 2

    # VERCEL は同日（offset=0）の本体+手数料でマッチ
    vercel = matched[matched["お取引内容"] == "VERCEL INC."].iloc[0]
    assert vercel["金額種別"] == "本体+手数料"
    assert int(vercel["日付ズレ日数"]) == 0
    assert vercel["取引No"] == "100"

    # CLAUDE.AI は±1日（offset=1）の本体+手数料でマッチ
    claude = matched[matched["お取引内容"] == "CLAUDE.AI SUBSCRIPTION"].iloc[0]
    assert claude["金額種別"] == "本体+手数料"
    assert int(claude["日付ズレ日数"]) == 1
    assert claude["取引No"] == "101"
