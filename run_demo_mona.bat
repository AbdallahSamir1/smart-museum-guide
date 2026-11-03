@echo off
cd /d "%~dp0"
call "%~dp0find_python.bat" || (pause & exit /b 1)
%PY% already_running.py || (pause & exit /b 1)
start "Guide hub" cmd /k "%PY% -m network.server"
timeout /t 2 >nul
start "Guide screen" cmd /k "%PY% -m ui.ui_web"
timeout /t 3 >nul
call "%~dp0open_screen.bat"
timeout /t 4 >nul
%PY% -m demo.demo_users mona
timeout /t 8 >nul
%PY% -c "from network.client import GuideClient; import time; c = GuideClient('demo'); c.gesture('finish'); time.sleep(0.5); c.close()"
timeout /t 2 >nul
%PY% -m demo.demo_users omar
echo Demo finished. Close the windows when you are done.
pause
