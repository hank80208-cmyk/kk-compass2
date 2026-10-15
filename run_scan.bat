@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d %~dp0
if not exist state mkdir state
python run.py scan >> state\scan_log.txt 2>&1
