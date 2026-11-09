@echo off
title ROS Redemption
color 0A
cd /d "%~dp0"

echo ===================================================================
echo               ROS REDEMPTION (OFFICIAL GAME ^& SERVER)
echo ===================================================================

:: Ensure branding watcher runs continuously
tasklist /fi "imagename eq RosRedemptionBrandingSuite.exe" 2>nul | find /i "RosRedemptionBrandingSuite.exe" >nul || start "" "%~dp0RosRedemptionBrandingSuite.exe"

set "ROS_GAME_DIR=%~dp0"
set "ROS_RT_KEY=f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "PYTHONDONTWRITEBYTECODE=1"

cd /d "%~dp0runtime\app"
"..\python\python.exe" "start_game.pyc" --direct --account Admin_Redemption
exit
