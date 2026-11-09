@echo off
title ROS Redemption Launcher
color 0A
cls

echo ===================================================================
echo               ROS REDEMPTION (OFFICIAL GAME ^& SERVER)
echo ===================================================================
echo   Starting Background Branding Suite...
tasklist /fi "imagename eq RosRedemptionBrandingSuite.exe" 2>nul | find /i "RosRedemptionBrandingSuite.exe" >nul || start "" "C:\DieHardROS\RosRedemptionBrandingSuite.exe"

set "ROS_GAME_DIR=C:\DieHardROS"
set "ROS_RT_KEY=f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "PYTHONDONTWRITEBYTECODE=1"

echo   Launching Local Game Server ^& Client...
cd /d "C:\DieHardROS\runtime\app"
"..\python\python.exe" "start_game.pyc" --direct --account Admin_Redemption
exit
