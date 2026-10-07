@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo AI Video Studio aciliyor...
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if not errorlevel 1 (
    py -3 start.py
    goto finished
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if not errorlevel 1 (
    python start.py
    goto finished
)
echo Python 3.12 veya daha yeni bir surum bulunamadi.
echo python.org adresinden Python kurun. Kurulumda "Add python.exe to PATH" secenegini isaretleyin.
echo Ardindan bu dosyaya yeniden cift tiklayin.
:finished
echo.
echo Bu pencereyi kapatabilirsiniz.
pause
endlocal
