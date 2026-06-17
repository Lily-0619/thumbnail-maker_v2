@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo BDM ツールランチャーを起動します...
rem 本体と同じく .venv の python を優先（依存はそこに入っている）。無ければ system python。
if exist ".\.venv\Scripts\python.exe" (
    ".\.venv\Scripts\python.exe" launcher.py
) else (
    python launcher.py
)
if errorlevel 1 (
    echo.
    echo 起動に失敗しました。依存をインストールしてください:
    if exist ".\.venv\Scripts\python.exe" (
        echo   ".\.venv\Scripts\python.exe" -m pip install customtkinter Pillow requests
    ) else (
        echo   python -m pip install customtkinter Pillow requests
    )
)
pause
