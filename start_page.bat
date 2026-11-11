@echo off
rem Starts the local page of the airship screen (constructor and game mode) on http://localhost:8765
rem Keep this window open while you work; close it to stop the server.
chcp 65001 >nul
cd /d "%~dp0"
title TWW3 barge page - http://localhost:8765
py -3.14 tools\web_serve.py --port 8765
echo.
echo The server has stopped. Press any key to close.
pause >nul
