@echo off
cd /d "%~dp0"
call "%~dp0find_python.bat" || (pause & exit /b 1)
%PY% already_running.py || (pause & exit /b 1)
echo Starting the Smart Museum Guide with %PY%
start "Guide hub" cmd /k "%PY% -m network.server"
timeout /t 2 >nul
start "Guide screen" cmd /k "%PY% -m ui.ui_web"
start "Bluetooth visitors" cmd /k "%PY% -m ble.ble_scanner --server 127.0.0.1:5050 --phone-id U101"
timeout /t 3 >nul
call "%~dp0open_screen.bat"
start "Camera gestures" cmd /k "%PY% -m tracking.camera --server 127.0.0.1:5050"
