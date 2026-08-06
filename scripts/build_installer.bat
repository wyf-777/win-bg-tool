@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

echo === Peel: build Windows installer ===
echo.

set "SKIP_EXE=0"
if /I "%~1"=="--installer-only" set "SKIP_EXE=1"
if /I "%~1"=="-i" set "SKIP_EXE=1"

if "%SKIP_EXE%"=="1" goto :check_dist

call scripts\build_exe.bat
if errorlevel 1 exit /b 1

:check_dist
if not exist "dist\Peel\Peel.exe" (
  echo [ERROR] dist\Peel\Peel.exe not found.
  echo Run scripts\build_exe.bat first, or omit --installer-only.
  exit /b 1
)
echo Found dist\Peel\Peel.exe

set "ISCC="
if defined INNO_SETUP_PATH (
  if exist "%INNO_SETUP_PATH%" set "ISCC=%INNO_SETUP_PATH%"
)
if not defined ISCC if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LocalAppData%\Programs\Inno Setup 7\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 7\ISCC.exe"

if not defined ISCC (
  where iscc >nul 2>&1
  if not errorlevel 1 for /f "delims=" %%I in ('where iscc 2^>nul') do set "ISCC=%%I"
)

if not defined ISCC (
  echo [ERROR] ISCC.exe not found. Install Inno Setup 6:
  echo   winget install --id JRSoftware.InnoSetup -e
  echo Or set INNO_SETUP_PATH to ISCC.exe full path.
  exit /b 1
)

echo Using: %ISCC%
echo Compiling packaging\peel_setup.iss ...
"%ISCC%" "%CD%\packaging\peel_setup.iss"
if errorlevel 1 (
  echo [ERROR] Inno Setup compile failed.
  exit /b 1
)

echo.
echo Done. Installer output in dist\
dir /b "dist\Peel-Setup-*.exe"
echo.
endlocal
