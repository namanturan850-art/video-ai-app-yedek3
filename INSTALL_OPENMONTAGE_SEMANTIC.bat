@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
py -3 -c "import sys;sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if not errorlevel 1 (
    py -3 install_openmontage.py --semantic-only
    goto finished
)
python -c "import sys;sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if not errorlevel 1 (
    python install_openmontage.py --semantic-only
    goto finished
)
echo Python 3.12 veya yenisi gerekli. python.org adresinden kurup tekrar deneyin.
:finished
echo.
pause
endlocal
