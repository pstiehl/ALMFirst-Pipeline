@echo off
REM ALM First SE Pipeline — Windows launcher. Double-click.
cd /d "%~dp0"
set PYTHON=
for %%P in (python py python3) do (
  %%P -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
  if not errorlevel 1 ( set PYTHON=%%P & goto :found )
)
echo Install Python 3.11+ from https://www.python.org/downloads/ (check "Add Python to PATH"), then double-click again.
pause & exit /b 1
:found
if not exist .venv %PYTHON% -m venv .venv
.venv\Scripts\python -m pip install -q --upgrade pip
.venv\Scripts\python -m pip install -q -r requirements.txt
if not exist data\processed\credit_unions.csv.gz .venv\Scripts\python scripts\build_data.py
echo Opening http://localhost:8501 ... (close this window to stop)
.venv\Scripts\python -m streamlit run app.py
