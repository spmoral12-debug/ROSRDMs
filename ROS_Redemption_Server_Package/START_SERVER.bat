@echo off
title ROS Redemption - Dedicated Master Server
color 0A
cd /d "%~dp0"

echo ===================================================================
echo             ROS REDEMPTION - DEDICATED MASTER SERVER
echo ===================================================================
echo   Lobby / Game Port  : 19000 (TCP / UDP)
echo   Battleground Port  : 19100 (UDP)
echo   Admin Dashboard    : http://127.0.0.1:8790/admin
echo   Update Mirror      : Ports 80 / 443
echo ===================================================================
echo.

set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "PYTHONDONTWRITEBYTECODE=1"

:: Start dedicated server
"%~dp0python\python.exe" "%~dp0run_server.py" %*

pause

