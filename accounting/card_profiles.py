"""
card_profiles.py

各デビットカードの照合に必要な属性をまとめた CardProfile 定義。

reconcile.py は登録された全プロファイルを順に処理し、明細CSVの読み込み・
カラム名・ステータス列の有無といったカード固有の差異をプロファイルに閉じ込める。
"""

from __future__ import annotations

import glob
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class CardProfile:
    card_id: str          # 出力サブディレクトリ名（"risona", "sbi", "lifecard" 等）
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
    # 明細CSVが「冒頭メタ情報＋明細セクション＋フッター」の3部構成のときに、
    # 明細セクションの先頭行を特定するためのマーカ（例：ライフカードの "明細No."）。
    # None の場合はファイル先頭がCSVヘッダーとして読み込まれる。
    header_marker: str | None = None
    # 明細セクションの末尾を特定するためのマーカ（例：ライフカードの "回数指定払"）。
    # None の場合はファイル末尾までを読み込む。
    footer_marker: str | None = None

    def load_debit(self) -> pd.DataFrame:
        """明細CSVを読み込んで返す。

        debit_pattern が glob パターンで複数ファイルにマッチする場合は結合し、
        日付 × 利用内容 × 金額 が一致する重複行を除外する。
        ファイルが1件もマッチしない場合は FileNotFoundError を raise。
        header_marker / footer_marker が指定されている場合は、明細セクションのみを抽出する。
        """
        paths = sorted(glob.glob(self.debit_pattern))
        if not paths:
            raise FileNotFoundError(
                f"明細CSVが見つかりません: {self.debit_pattern}"
            )

        frames = [self._read_one(p) for p in paths]
        df = pd.concat(frames, ignore_index=True)

        # 複数ファイルから読み込んだ場合のみ、月またぎで重複した行を除外する。
        # 単一ファイルでは元データの重複（同日同店舗で2回利用など）を保持する。
        if len(paths) >= 2:
            dedup_cols = [self.date_col, self.merchant_col, self.amount_col]
            df = df.drop_duplicates(subset=dedup_cols).reset_index(drop=True)
        return df

    def _read_one(self, path: str) -> pd.DataFrame:
        """1ファイル分の明細CSVを読み込む。

        header_marker が None の場合は通常の pd.read_csv で全体を読む。
        指定されている場合は明細セクションのみを切り出してから読む。
        """
        if self.header_marker is None:
            return pd.read_csv(
                path, encoding=self.debit_encoding, dtype=str,
            ).fillna("")
        return self._read_with_markers(path)

    def _read_with_markers(self, path: str) -> pd.DataFrame:
        """header_marker / footer_marker で明細セクションを切り出して読む。"""
        with open(path, encoding=self.debit_encoding) as fp:
            lines = fp.readlines()

        header_idx: int | None = None
        for i, line in enumerate(lines):
            if line.startswith(self.header_marker):  # type: ignore[arg-type]
                header_idx = i
                break
        if header_idx is None:
            raise ValueError(
                f"明細CSV {path!r} に header_marker {self.header_marker!r} で始まる行が見つかりません"
            )

        section: list[str] = []
        for line in lines[header_idx:]:
            if self.footer_marker is not None and line.startswith(self.footer_marker):
                break
            if line.strip():
                section.append(line)
        return pd.read_csv(StringIO("".join(section)), dtype=str).fillna("")


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
    "lifecard": CardProfile(
        card_id="lifecard",
        account_name="ミライノ カード(MasterCard)ミライノカード Bu",
        date_col="利用日",
        amount_col="利用金額",
        merchant_col="利用先",
        has_status=False,
        debit_pattern=str(Path("data/accounting/lifecard_meisai_*.csv")),
        # ライフカードは利用日と仕訳日がほぼ同日なのでズレ吸収不要
        date_tolerance_days=0,
        # CSV冒頭にメタ情報（支払日・会員氏名・契約内容など）があり、明細セクションは
        # "明細No.,..." で始まる。"回数指定払 内訳表" 以降はフッターなので除外する。
        header_marker="明細No.",
        footer_marker="回数指定払",
    ),
}
