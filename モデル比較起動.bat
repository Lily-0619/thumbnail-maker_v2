@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo モデル / LoRA 比較ツールを起動します...
python tools\model_tester\model_tester_app.py
if errorlevel 1 (
    echo.
    echo 起動に失敗しました。依存をインストールしてください:
    echo   pip install -r tools\model_tester\requirements.txt
    pause
)
