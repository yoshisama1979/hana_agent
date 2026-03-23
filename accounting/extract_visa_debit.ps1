# extract_visa_debit.ps1
# 仕訳帳CSVからVISAデビット（★要確認）の行を抽出する

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PyScript  = Join-Path $ScriptDir "extract_visa_debit.py"

python $PyScript @args
