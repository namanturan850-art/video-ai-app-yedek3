@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Once START_NAMAN.bat ile NAMAN kurulumunu tamamlayin.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import pytest" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
  if errorlevel 1 exit /b 1
)
echo Bu kontrol yalniz gecici sentetik veri kullanir; projelerinizi degistirmez.
".venv\Scripts\python.exe" scripts\windows_editor_check.py --webview2 --output windows-editor-report.json
echo Sonuc windows-editor-report.json dosyasina yazildi.
pause
