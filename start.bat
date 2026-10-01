@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -c "import streamlit, pandas, sklearn, lightgbm, gspread" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -m streamlit run app.py --server.address localhost --browser.gatherUsageStats false
if errorlevel 1 goto :failed
exit /b
:failed
echo Setup or startup failed. Please share the error shown above.
pause
