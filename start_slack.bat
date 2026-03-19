@echo off
chcp 65001 >/dev/null
set PYTHONUTF8=1
cd /d C:\openjarvis
echo Starting Jarvis Slack listener...
uv run python slack_listener.py
pause
