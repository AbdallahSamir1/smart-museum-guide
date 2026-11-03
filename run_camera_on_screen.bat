@echo off
cd /d "%~dp0"
call "%~dp0find_python.bat" || (pause & exit /b 1)
echo Camera connected to the guide screen. Press q in the camera window to quit.
%PY% -m tracking.camera --server 127.0.0.1:5050
pause
