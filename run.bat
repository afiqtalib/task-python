@echo off
rem One-click start: creates the virtual environment on first run, then opens the app.
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto :install

set "PY="
if exist "C:\laragon\bin\python\python-3.10\python.exe" set "PY=C:\laragon\bin\python\python-3.10\python.exe"
if not defined PY (where py >nul 2>nul && set "PY=py -3")
if not defined PY (
  echo Python 3.10+ was not found. Install it from https://www.python.org/downloads/ and run this file again.
  pause
  exit /b 1
)
echo Creating virtual environment...
%PY% -m venv .venv || (echo Could not create the virtual environment. & pause & exit /b 1)

:install
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || (echo Package installation failed. & pause & exit /b 1)

echo.
echo  Claim form running at http://127.0.0.1:5000   (close this window to stop)
echo.
start "" "http://127.0.0.1:5000"
".venv\Scripts\python.exe" app.py
