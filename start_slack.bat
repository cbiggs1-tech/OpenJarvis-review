@echo off
chcp 65001 >/dev/null
set PYTHONUTF8=1
cd /d C:\openjarvis

echo Stopping any existing Jarvis Slack listener...
taskkill /F /FI "WINDOWTITLE eq Jarvis Slack*" >/dev/null 2>&1
for /f "tokens=2" %%i in ('tasklist /fi "imagename eq python.exe" /fo table /nh 2^>/dev/null ^| findstr python') do (
    wmic process %%i get commandline 2>/dev/null | findstr "slack_listener" >/dev/null && taskkill /F /PID %%i >/dev/null 2>&1
)

echo Starting Jarvis Slack listener...
title Jarvis Slack Listener
uv run python slack_listener.py
pause
