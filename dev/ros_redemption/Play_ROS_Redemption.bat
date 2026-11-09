@echo off
title ROS Redemption - Client Game Launcher
color 0E

for %%I in ("%~dp0..\..") do set "BASE_DIR=%%~fI"

echo ===================================================================
echo               ROS REDEMPTION - CLIENT GAME LAUNCHER
echo ===================================================================
echo [INFO] Game Directory: %BASE_DIR%
echo [INFO] Account Profile: Admin_Redemption
echo [INFO] Server Target  : ROS-Redemption-Official (Port 19000)
echo [INFO] Launching game client with Hook Injection...
echo ===================================================================

set "ROS_GAME_DIR=%BASE_DIR%"
set "ROS_RT_KEY=f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "PYTHONDONTWRITEBYTECODE=1"

if exist "%BASE_DIR%\runtime\app\start_second.pyc" (
    cd /d "%BASE_DIR%\runtime\app"
    "..\python\python.exe" "start_second.pyc" --account Admin_Redemption
) else (
    cd /d "C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app"
    "..\python\python.exe" "start_second.pyc" --account Admin_Redemption
)
pause
