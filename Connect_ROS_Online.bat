@echo off
setlocal
title ROS Redemption Online Playtest
cd /d "%~dp0"

set "ROS_GAME_DIR=%CD%"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "PYTHONDONTWRITEBYTECODE=1"

if exist "runtime\python\python.exe" (
    set "PY_EXE=runtime\python\python.exe"
) else (
    set "PY_EXE=ROS_Redemption_Server_Package\python\python.exe"
)

"%PY_EXE%" -u "connect_online.py" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Exited with code %EXIT_CODE%.
    pause
)
exit /b %EXIT_CODE%

