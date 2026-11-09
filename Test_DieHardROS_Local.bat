@echo off
setlocal
title DieHardROS Local Playtest
cd /d "%~dp0"
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
