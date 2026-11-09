@echo off
title ROS Redemption - Client Game Launcher
color 0E
echo ===================================================================
echo               ROS REDEMPTION - CLIENT GAME LAUNCHER
echo ===================================================================
echo [INFO] Game Directory: C:\DieHardROS
echo [INFO] Account Profile: Admin_Redemption
echo [INFO] Server Target  : ROS-Redemption-Official (Port 19000)
echo [INFO] Launching game client with Hook Injection...
echo ===================================================================

set "ROS_GAME_DIR=C:\DieHardROS"
set "ROS_RT_KEY=f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "PYTHONDONTWRITEBYTECODE=1"

cd /d "C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app"
"..\python\python.exe" "start_second.pyc" --account Admin_Redemption
pause
