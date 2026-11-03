@echo off
cd /d "%~dp0"
echo === Python versions on this computer ===
py -0
echo.
set PYV=
for %%v in (3.11 3.12 3.13 3.10 3.9) do (
  if not defined PYV ( py -%%v -c "pass" >nul 2>&1 && set "PYV=%%v" )
)
if not defined PYV (
  echo No Python 3.9 to 3.13 found. Install Python 3.11 from python.org, then run this file again.
  pause
  exit /b 1
)
echo Using Python %PYV%
set "REDO="
if exist .venv if not exist .venv\Scripts\activate.bat set REDO=1
if exist .venv if not exist .venv\Scripts\python.exe set REDO=1
if defined REDO echo The .venv folder is incomplete: making it again.
if defined REDO py -%PYV% -m venv --clear .venv
if not exist .venv py -%PYV% -m venv .venv
if not exist .venv\Scripts\activate.bat goto novenv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
echo.
echo === Tests ===
python -m tests.test_gestures
python -m tests.test_sockets
python -m tests.test_ble
python -m tests.test_context
python -m tests.test_web
echo.
echo Done. Close this window.
pause
exit /b 0
:novenv
echo Could not make the .venv folder. Close the other Python windows and run this file again.
pause
exit /b 1
