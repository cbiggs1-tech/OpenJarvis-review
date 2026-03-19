@echo off
chcp 65001 >/dev/null
set PYTHONUTF8=1
cd /d C:\openjarvis
uv run jarvis %*
