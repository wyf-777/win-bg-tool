@echo off
cd /d "%~dp0"
set "PYTHON_EXE=D:\Tools\Python\python.exe"
if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" -m app.main
) else (
    python -m app.main
)
if errorlevel 1 pause
