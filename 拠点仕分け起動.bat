@echo off
chcp 65001 > nul
rem Base image sorter launcher. Runs from the bat's own folder,
rem so it works no matter which drive the repo lives on.
cd /d "%~dp0"
if exist ".\.venv\tcl\tcl8.6\init.tcl" set "TCL_LIBRARY=%CD%\.venv\tcl\tcl8.6"
if exist ".\.venv\tcl\tk8.6\tk.tcl" set "TK_LIBRARY=%CD%\.venv\tcl\tk8.6"
echo Starting base image sorter...
rem Prefer .venv python (deps live there); fall back to system python.
if exist ".\.venv\Scripts\python.exe" (
    ".\.venv\Scripts\python.exe" tools\base_image_sorter\base_image_sorter_app.py
) else (
    python tools\base_image_sorter\base_image_sorter_app.py
)
if errorlevel 1 (
    echo.
    echo Failed to start. Install dependencies:
    if exist ".\.venv\Scripts\python.exe" (
        echo   ".\.venv\Scripts\python.exe" -m pip install -r tools\base_image_sorter\requirements.txt
    ) else (
        echo   python -m pip install -r tools\base_image_sorter\requirements.txt
    )
)
pause
