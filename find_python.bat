@echo off
rem Finds a Python that has the project's libraries and puts its command in PY.
rem The run_*.bat files use it:  call "%~dp0find_python.bat" || (pause & exit /b 1)
set "PY="
set "NEED=import mediapipe, cv2, numpy, dollarpy"
if exist "%~dp0.venv\Scripts\python.exe" "%~dp0.venv\Scripts\python.exe" -c "%NEED%" >nul 2>&1 && set PY="%~dp0.venv\Scripts\python.exe"
for %%v in (3.13 3.12 3.11 3.10 3.9) do if not defined PY py -%%v -c "%NEED%" >nul 2>&1 && set "PY=py -%%v"
if not defined PY py -c "%NEED%" >nul 2>&1 && set "PY=py"
if not defined PY python -c "%NEED%" >nul 2>&1 && set "PY=python"
if defined PY exit /b 0
echo.
echo No Python with the project's libraries (mediapipe, opencv-python, numpy, dollarpy) was found.
echo Run setup_and_test.bat once: it installs them. Then start this file again.
exit /b 1
