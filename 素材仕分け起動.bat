@echo off
rem エフェクト素材仕分けツール起動用。bat の置き場所を基準に動くので、
rem リポジトリをどのドライブに置いても動作する。
cd /d "%~dp0"
if exist ".\.venv\Scripts\python.exe" (
    ".\.venv\Scripts\python.exe" tools\effect_sorter\effect_sorter_app.py
) else (
    python tools\effect_sorter\effect_sorter_app.py
)
pause
