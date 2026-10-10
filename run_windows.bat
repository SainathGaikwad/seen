@echo off
REM SEEN — one-click setup and run on Windows (use your normal network, not a locked-down VPN).
REM   run_windows.bat          full: install, load Cricsheet, live pipeline, open app
REM   run_windows.bat load     only download/load Cricsheet data
REM   run_windows.bat run      only the pipeline (attention + gap + XI + kits)
REM   run_windows.bat app      only open the app
REM   run_windows.bat fixture  pipeline with the labelled SYNTHETIC attention set (no network needed)
setlocal
cd /d "%~dp0"
set MODE=%1

where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)
%PY% --version >nul 2>nul || (
  echo Python 3.10 or newer is required. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause & exit /b 1
)

if not exist .venv (
  echo === Creating virtual environment ===
  %PY% -m venv .venv || (echo venv failed & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
if not exist .venv\Lib\site-packages\streamlit (
  echo === Installing requirements (2-5 minutes the first time) ===
  python -m pip install --upgrade pip >nul
  pip install -r requirements.txt || (echo pip install failed & pause & exit /b 1)
)
if not exist .env copy .env.example .env >nul

if "%MODE%"=="app" goto app
if "%MODE%"=="run" goto run
if "%MODE%"=="fixture" goto fixture

echo.
echo === Step 1/3: loading Cricsheet data (downloads are cached; 1-3 minutes) ===
python -m seen.pipeline load --source cricsheet -v || (echo LOAD FAILED - check your internet connection & pause & exit /b 1)
if "%MODE%"=="load" goto done

:run
echo.
echo === Step 2/3: live attention data + gap model + Unseen XI + story kits (5-10 minutes) ===
echo (close the SEEN app first if it is open - the database can be written by one program at a time)
python -m seen.pipeline run --attention live -v || (echo RUN FAILED & pause & exit /b 1)
goto app

:fixture
python -m seen.pipeline run --attention fixture -v || (echo RUN FAILED & pause & exit /b 1)

:app
echo.
echo === Step 3/3: opening the SEEN app in your browser (Ctrl+C in this window to stop) ===
streamlit run app\Home.py
:done
pause
