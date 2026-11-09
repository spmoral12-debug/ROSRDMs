@echo off
setlocal
title ROS REDEMPTION - Local Playtest
cd /d "%~dp0"

:: Start branding suite to watch window titles and apply ROS Redemption branding
tasklist /fi "imagename eq RosRedemptionBrandingSuite.exe" 2>nul | find /i "RosRedemptionBrandingSuite.exe" >nul || start "" "%~dp0RosRedemptionBrandingSuite.exe"

set "ROS_GAME_DIR=%CD%"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "PYTHONDONTWRITEBYTECODE=1"
"runtime\python\python.exe" -u "start_diehard_local.py" --direct --local-auth --host 127.0.0.1 %*
set "ROS_EXIT=%ERRORLEVEL%"
if not "%ROS_EXIT%"=="0" (
    echo.
    echo Local playtest exited with code %ROS_EXIT%.
    pause
)
exit /b %ROS_EXIT%
