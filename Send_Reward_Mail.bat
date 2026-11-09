@echo off
title ROS Redemption - Send In-Game Reward
color 0E
cd /d "%~dp0"

set PY="%~dp0runtime\python\python.exe"
if not exist %PY% set PY=python

%PY% "%~dp0send_reward_mail.py"
echo.
pause

