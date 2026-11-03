@echo off
cd /d "%~dp0"
echo Installing and testing, please wait. Output goes to install_log.txt
rem UTF-8, so Arabic text in the log cannot stop a test
set PYTHONIOENCODING=utf-8
call :main > install_log.txt 2>&1
echo Finished. You can close this window.
timeout /t 5 >nul
exit /b
:main
py -0
set PYV=
for %%v in (3.11 3.12 3.13 3.10 3.9) do (
  if not defined PYV ( py -%%v -c "pass" >nul 2>&1 && set "PYV=%%v" )
)
if not defined PYV ( echo No Python 3.9 to 3.13 found. & exit /b 1 )
echo Using Python %PYV%
set "REDO="
if exist .venv if not exist .venv\Scripts\activate.bat set REDO=1
if exist .venv if not exist .venv\Scripts\python.exe set REDO=1
if defined REDO echo The .venv folder is incomplete: making it again.
if defined REDO py -%PYV% -m venv --clear .venv
if not exist .venv py -%PYV% -m venv .venv
if not exist .venv\Scripts\activate.bat goto novenv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
echo === TESTS ===
python -m tests.test_gestures
python -m tests.test_sockets
python -m tests.test_ble
python -m tests.test_context
python -m tests.test_web
python -c "import mediapipe, cv2; print('mediapipe', mediapipe.__version__, 'opencv', cv2.__version__)"
python -c "from tracking.hand_tracker import HandTracker; t=HandTracker(); print('hand tracker ready, legacy API' if t.legacy else 'hand tracker ready, tasks API')"
echo === DONE ===
exit /b 0
:novenv
echo Could not make the .venv folder. Close the other Python windows and run this file again.
exit /b 1
