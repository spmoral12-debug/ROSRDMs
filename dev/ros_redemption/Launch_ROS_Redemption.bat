@echo off
title ROS Redemption Launcher
color 0A
cls

for %%I in ("%~dp0..\..") do set "BASE_DIR=%%~fI"

echo ===================================================================
echo               ROS REDEMPTION (OFFICIAL GAME ^& SERVER)
echo ===================================================================
echo   Starting Background Branding Suite...
tasklist /fi "imagename eq RosRedemptionBrandingSuite.exe" 2>nul | find /i "RosRedemptionBrandingSuite.exe" >nul || start "" "%BASE_DIR%\RosRedemptionBrandingSuite.exe"

set "ROS_GAME_DIR=%BASE_DIR%"
set "ROS_RT_KEY=f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "PYTHONDONTWRITEBYTECODE=1"

echo   Launching Local Game Server ^& Client...
if exist "%BASE_DIR%\runtime\app\start_game.pyc" (
    cd /d "%BASE_DIR%\runtime\app"
    "..\python\python.exe" "start_game.pyc" --direct --account Admin_Redemption
) else (
    cd /d "C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app"
    "..\python\python.exe" "start_game.pyc" --direct --account Admin_Redemption
)
exit
