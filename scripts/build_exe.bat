@echo off
setlocal
cd /d "%~dp0.."

echo === Peel win-bg-tool: build exe ===
echo.

if not exist "models\u2netp.onnx" (
  echo [ERROR] models\u2netp.onnx not found. Place U2-Net lite weights first.
  exit /b 1
)

python -m pip install -q -r requirements.txt "pyinstaller>=6.0"
if errorlevel 1 exit /b 1

echo Building with PyInstaller...
python -m PyInstaller --noconfirm --clean peel.spec
if errorlevel 1 exit /b 1

echo.
echo Done. Output:
echo   dist\Peel\Peel.exe
echo   dist\Peel\_internal\   ^(REQUIRED - ship whole folder^)
echo   dist\Peel\models\u2netp.onnx  ^(shipped U2-Net lite^)
echo.
echo Ship the entire dist\Peel\ directory. Do NOT copy only Peel.exe.
echo Packaging notes / checklist: docs\packaging.md
echo.
endlocal
