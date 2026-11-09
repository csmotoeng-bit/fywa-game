@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 goto :fail
)
echo Installing project dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail
echo.
echo FYWA is starting at http://localhost:5000
".venv\Scripts\python.exe" app.py
pause
exit /b 0
:fail
echo.
echo Setup failed. Make sure Python 3.12 or later is installed and available.
pause
exit /b 1
