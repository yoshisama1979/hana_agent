# 法人決算支援ツール - 使い方ガイド

月次の仕訳作業を効率化するためのツール群です。
会計ソフトからエクスポートしたCSVを加工・分析することで、決算準備の手間を削減します。

---

## ディレクトリ構成

```
accounting/
├── README.md                   # このファイル
├── extract_visa_debit.sh       # 実行用シェルスクリプト
├── extract_visa_debit.py       # VISAデビット抽出プログラム
└── data/
    ├── 仕訳帳.csv               # 会計ソフトからエクスポートした仕訳帳（入力）
    └── output/
        └── visa_debit_要確認.csv  # 抽出結果（出力）
```

---

## 前提条件

- **Python 3.x**（conda環境）と **pandas** がインストールされていること
- **Git Bash** などのbash環境があること

---

## ツール一覧

### extract_visa_debit.sh — VISAデビット仕訳の抽出

仕訳帳CSVの中から、以下の**両方の条件**に合う行を抽出してCSVに書き出します。

| 条件 | 内容 |
|------|------|
| 借方勘定科目 | `★要確認` である |
| 摘要 | `VISAデビ` で始まる |

#### 使い方

```bash
# accounting/ ディレクトリに移動
cd /c/xampp/htdocs/hana_agent/accounting

# デフォルトパスで実行
bash extract_visa_debit.sh

# 入出力ファイルを指定して実行
bash extract_visa_debit.sh data/仕訳帳.csv data/output/出力先.csv
```

#### 入力ファイル

会計ソフト（freee等）から仕訳帳をCSV形式でエクスポートし、以下のパスに配置してください。

```
accounting/data/仕訳帳.csv
```

- 文字コード：**Shift-JIS**（会計ソフトの標準エクスポート形式のまま可）
- 必須列：`借方勘定科目`、`摘要`

#### 出力ファイル

```
accounting/data/output/visa_debit_要確認.csv
```

- 文字コード：**UTF-8（BOM付き）** — Excelで開いても文字化けしません
- 内容：入力CSVと同じ列構成で、条件に合う行のみ収録

---

## 月次の作業フロー

```
1. 会計ソフトから仕訳帳をCSVでエクスポート
        ↓
2. data/仕訳帳.csv として保存
        ↓
3. bash extract_visa_debit.sh を実行
        ↓
4. data/output/visa_debit_要確認.csv をExcelやスプレッドシートで開く
        ↓
5. 内容を確認し、借方勘定科目を正しい科目に修正
        ↓
6. 修正済みデータを会計ソフトにインポート
```

---

## トラブルシューティング

### 「FileNotFoundError」と表示される

`data/仕訳帳.csv` が存在するか確認してください。

```bash
ls data/仕訳帳.csv
```

### 出力CSVをExcelで開くと文字化けする

出力ファイルはUTF-8 BOM付きで書き出されているため、通常のExcelであれば自動で認識されます。
文字化けする場合はExcelの「データ」→「テキストファイル」からインポートし、文字コード「UTF-8」を選択してください。

### 抽出件数が0件になる

- 仕訳帳に `★要確認` の行が存在するか確認してください
- 摘要の表記が `VISAデビ` から始まっているか確認してください（全角・半角に注意）
