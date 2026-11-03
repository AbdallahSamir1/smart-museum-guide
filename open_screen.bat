@echo off
rem Opens the guide screen in its own window (Edge or Chrome), allowed to read the story aloud
rem without a click first. It uses its own browser profile, so the normal browser is not changed.
set "URL=%~1"
if not defined URL set "URL=http://127.0.0.1:8000"
set "BROWSER="
for %%b in ("%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" "%ProgramFiles%\Google\Chrome\Application\chrome.exe" "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe") do if not defined BROWSER if exist %%b set "BROWSER=%%~b"
if not defined BROWSER goto plain
start "" "%BROWSER%" --user-data-dir="%LOCALAPPDATA%\SmartMuseumGuideScreen" --autoplay-policy=no-user-gesture-required --no-first-run --no-default-browser-check --start-maximized --app="%URL%"
exit /b 0
:plain
rem no Edge or Chrome found: the normal browser; click the speaker button once for the voice
start "" "%URL%"
exit /b 0
