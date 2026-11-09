@echo off
title ROS Redemption Launcher
cd /d "%~dp0"

:: Start Branding Suite if not running
tasklist /fi "imagename eq RosRedemptionBrandingSuite.exe" 2>nul | find /i "RosRedemptionBrandingSuite.exe" >nul || start "" "%~dp0RosRedemptionBrandingSuite.exe"

:: Start Valorant-Style Launcher UI
start "" "%~dp0ROS_Redemption_Launcher.exe"
exit
