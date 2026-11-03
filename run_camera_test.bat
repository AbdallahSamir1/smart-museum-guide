@echo off
cd /d "%~dp0"
call "%~dp0find_python.bat" || (pause & exit /b 1)
echo Show your hand to the camera. Press q in the camera window to quit.
%PY% -m tracking.camera
pause
