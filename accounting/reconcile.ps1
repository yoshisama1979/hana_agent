# reconcile.ps1
# りそなデビット明細と仕訳帳を照合して勘定科目を推定する

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir

Push-Location $ProjectDir
python -m accounting.reconcile @args
Pop-Location
