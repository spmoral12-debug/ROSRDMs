@echo off
title ROS Redemption Launcher
cd /d "%~dp0"
if exist "%~dp0ROS_Redemption.exe" (
    start "" "%~dp0ROS_Redemption.exe"
    exit
)
if exist "runtime\python\python.exe" (
    start "" "runtime\python\python.exe" "start_diehard_local.py" --direct
) else (
    start "" "python" "start_diehard_local.py" --direct
)
exit
