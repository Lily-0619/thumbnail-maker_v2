@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo モデル / LoRA 比較ツールを起動します...
rem 本体と同じく .venv の python を優先（依存はそこに入っている）。無ければ system python。
if exist ".\.venv\Scripts\python.exe" (
    ".\.venv\Scripts\python.exe" tools\model_tester\model_tester_app.py
) else (
    python tools\model_tester\model_tester_app.py
)
if errorlevel 1 (
    echo.
    echo 起動に失敗しました。依存をインストールしてください:
    if exist ".\.venv\Scripts\python.exe" (
        echo   ".\.venv\Scripts\python.exe" -m pip install -r tools\model_tester\requirements.txt
    ) else (
        echo   python -m pip install -r tools\model_tester\requirements.txt
    )
)
pause
