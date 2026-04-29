# 環境固有の設定メモ

## Pythonの実行方法

このプロジェクトはWSL上で動作しており、シェル環境はGit Bash on Windows（platform: win32）です。

- `python3` / `conda` はGit BashおよびWSL bashから直接呼び出せません
- Pythonが必要な場合は **PowerShell経由** で実行してください

### 使用可能なconda環境

```
powershell -Command "conda env list"
```

| 環境名 | パス |
|---|---|
| base | C:\ProgramData\anaconda3 |
| my_env | C:\ProgramData\anaconda3\envs\my_env |
| marukoma | C:\Users\yoshi\.conda\envs\marukoma |
| myenv_py39 | C:\Users\yoshi\.conda\envs\myenv_py39 |
| task-orchestrator | C:\Users\yoshi\.conda\envs\task-orchestrator |

### 実行例

```bash
# スクリプト実行
powershell -Command "conda run -n base python -c 'print(\"hello\")'"

# ファイル実行
powershell -Command "conda run -n base python C:/path/to/script.py"
```

### 注意事項

- `cmd /c "..."` はUNCパス（`\\wsl.localhost\...`）から起動するとエラーになります
- `wsl -e bash -c "conda ..."` もcondaが見つからずエラーになります
- PowerShell経由が唯一の安定した方法です
