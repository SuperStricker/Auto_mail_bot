@echo off
title Auto Mail Bot - Local Runner
cd /d "%~dp0"
echo ========================================================
echo   Auto Mail Bot - Local Runner (Desktop Mode)
echo   Listening for Telegram Messages (@Shuaib_Job_Mailer_bot)...
echo ========================================================
python run_local.py
pause
