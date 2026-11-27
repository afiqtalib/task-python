@echo off
rem Builds the Windows installer: dist\installer\DBT-Claim-Setup-<version>.exe
rem Needs the .venv (run run.bat once) and Inno Setup 6 (https://jrsoftware.org/isdl.php).
setlocal
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo The .venv folder was not found. Run run.bat once first, or follow README.md.
  goto :fail
)

rem A .venv created by uv has no pip. Add it so the build tools can be installed.
"%PY%" -m pip --version >nul 2>nul || "%PY%" -m ensurepip --upgrade >nul || goto :fail

echo [1/4] Installing build tools...
"%PY%" -m pip install --disable-pip-version-check -q -r requirements-build.txt || goto :fail

echo [2/4] Running tests...
"%PY%" -m pytest -q || goto :fail

echo [3/4] Building ClaimForm.exe...
"%PY%" installer\make_icon.py build\ClaimForm.ico || goto :fail
"%PY%" -m PyInstaller --noconfirm --clean --log-level WARN --distpath dist --workpath build\pyinstaller installer\ClaimForm.spec || goto :fail

echo [4/4] Building Setup.exe...
set "ISCC="
for %%P in ("%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe") do if exist %%P set "ISCC=%%~P"
if not defined ISCC (
  echo Inno Setup 6 was not found. Install it from https://jrsoftware.org/isdl.php and run this file again.
  goto :fail
)
"%ISCC%" /Q installer\ClaimForm.iss || goto :fail

echo.
echo Done. Installer:
dir /b dist\installer\DBT-Claim-Setup-*.exe
echo (in %CD%\dist\installer)
pause
exit /b 0

:fail
echo.
echo Build failed - see the messages above.
pause
exit /b 1
