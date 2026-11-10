@echo off
title ROS Redemption - Backend Server
color 0B
echo ===================================================================
echo               ROS REDEMPTION - DEDICATED SERVER ENGINE
echo ===================================================================
echo [INFO] Game Directory: C:\DieHardROS
echo [INFO] Server Name   : ROS-Redemption-Official (Port 19000)
echo [INFO] Battle Server : Battle Host Active (Port 19100)
echo [INFO] Web Admin API : http://127.0.0.1:8790/admin
echo [INFO] Controller UI : http://127.0.0.1:8888
echo ===================================================================

set "ROS_GAME_DIR=%~dp0"
set "ROS_RT_KEY=f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "PYTHONDONTWRITEBYTECODE=1"

if exist "%~dp0runtime\app\start_game.pyc" (
    cd /d "%~dp0runtime\app"
    "..\python\python.exe" "start_game.pyc" --server-only
) else (
    cd /d "C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app"
    "..\python\python.exe" "start_game.pyc" --server-only
)
pause
