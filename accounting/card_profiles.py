"""
card_profiles.py

各デビットカードの照合に必要な属性をまとめた CardProfile 定義。

reconcile.py は登録された全プロファイルを順に処理し、明細CSVの読み込み・
カラム名・ステータス列の有無といったカード固有の差異をプロファイルに閉じ込める。
"""

from __future__ import annotations

import glob
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class CardProfile:
    card_id: str          # 出力サブディレクトリ名（"risona", "sbi"）
    account_name: str     # 仕訳帳側で使われる補助科目名
    date_col: str         # 明細CSVの利用日カラム名
    amount_col: str       # 明細CSVの金額カラム名
    merchant_col: str     # 明細CSVの利用内容カラム名
    has_status: bool      # ステータス列を持つか（持たないカードは全行確定扱い）
    debit_pattern: str    # 明細CSVのパス（単一ファイル or glob パターン）
    debit_encoding: str = "cp932"
    # 日付許容ズレ。0 なら厳格一致のみ、>0 なら段階マッチで ±N日まで吸収する。
    date_tolerance_days: int = 0
    # フォールバック用の手数料カラム。指定すると amount_col + Σ(fee_cols) でも再照合する。
    # SBIでは海外通貨取引が「本体+海外事務手数料」の合算で仕訳帳に計上されるケース対応。
    fee_cols: tuple[str, ...] = ()

    def load_debit(self) -> pd.DataFrame:
        """明細CSVを読み込んで返す。

        debit_pattern が glob パターンで複数ファイルにマッチする場合は結合し、
        日付 × 利用内容 × 金額 が一致する重複行を除外する。
        ファイルが1件もマッチしない場合は FileNotFoundError を raise。
        """
        paths = sorted(glob.glob(self.debit_pattern))
        if not paths:
            raise FileNotFoundError(
                f"明細CSVが見つかりません: {self.debit_pattern}"
            )

        frames = [
            pd.read_csv(p, encoding=self.debit_encoding, dtype=str).fillna("")
            for p in paths
        ]
        df = pd.concat(frames, ignore_index=True)

        # 複数ファイルから読み込んだ場合のみ、月またぎで重複した行を除外する。
        # 単一ファイルでは元データの重複（同日同店舗で2回利用など）を保持する。
        if len(paths) >= 2:
            dedup_cols = [self.date_col, self.merchant_col, self.amount_col]
            df = df.drop_duplicates(subset=dedup_cols).reset_index(drop=True)
        return df


PROFILES: dict[str, CardProfile] = {
    "risona": CardProfile(
        card_id="risona",
        account_name="りそな銀行大手支店普通0073514",
        date_col="利用日",
        amount_col="金額",
        merchant_col="利用内容",
        has_status=True,
        debit_pattern=str(Path("data/accounting/risona_debit.csv")),
    ),
    "sbi": CardProfile(
        card_id="sbi",
        account_name="住信SBI106代表口座 - 円普通2212165",
        date_col="お取引日",
        amount_col="お取引金額",
        merchant_col="お取引内容",
        has_status=False,
        debit_pattern=str(Path("data/accounting/meisai_*.csv")),
        # SBIは「カード利用日」と「口座引落日」が最大2週間程度ズレるため段階マッチで吸収する
        # （定期決済系でカード利用日から実引落まで9〜11日ほどかかるケースを想定）
        date_tolerance_days=14,
        # 海外通貨取引は仕訳帳側で「本体+海外事務手数料」の合算金額で1行に計上される
        fee_cols=("海外事務手数料",),
    ),
}
