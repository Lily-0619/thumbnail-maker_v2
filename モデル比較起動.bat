@echo off
chcp 65001 > nul
cd /d "%~dp0"
if exist ".\.venv\tcl\tcl8.6\init.tcl" set "TCL_LIBRARY=%CD%\.venv\tcl\tcl8.6"
if exist ".\.venv\tcl\tk8.6\tk.tcl" set "TK_LIBRARY=%CD%\.venv\tcl\tk8.6"
echo Starting Model / LoRA comparison tool...
rem Prefer .venv python (deps live there); fall back to system python.
if exist ".\.venv\Scripts\python.exe" (
    ".\.venv\Scripts\python.exe" tools\model_tester\model_tester_app.py
) else (
    python tools\model_tester\model_tester_app.py
)
if errorlevel 1 (
    echo.
    echo Failed to start. Install dependencies:
    if exist ".\.venv\Scripts\python.exe" (
        echo   ".\.venv\Scripts\python.exe" -m pip install -r tools\model_tester\requirements.txt
    ) else (
        echo   python -m pip install -r tools\model_tester\requirements.txt
    )
)
pause
