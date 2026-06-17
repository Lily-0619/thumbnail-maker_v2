@echo off
chcp 65001 > nul
cd /d "%~dp0"
if exist ".\.venv\tcl\tcl8.6\init.tcl" set "TCL_LIBRARY=%CD%\.venv\tcl\tcl8.6"
if exist ".\.venv\tcl\tk8.6\tk.tcl" set "TK_LIBRARY=%CD%\.venv\tcl\tk8.6"
.\.venv\Scripts\python.exe main.py
pause
