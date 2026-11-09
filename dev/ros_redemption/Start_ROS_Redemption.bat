@echo off
title ROS Redemption - Master Server Suite
color 0A

for %%I in ("%~dp0..\..") do set "BASE_DIR=%%~fI"

echo ===================================================================
echo               ROS REDEMPTION - MASTER SERVER SUITE
echo ===================================================================
echo [1] PLAY ROS REDEMPTION (All-In-One: Auto Server + Game Launch)
echo [2] Start Dedicated Server Only (Background Server Host)
echo [3] Launch Client Window (Connect to Running Dedicated Server)
echo [4] Open Web Controller Panel (http://127.0.0.1:8888)
echo ===================================================================
echo.
set /p choice="Enter choice [1-4] (Default 1): "
if "%choice%"=="" set choice=1

if "%choice%"=="1" goto play_all_in_one
if "%choice%"=="2" goto start_server_only
if "%choice%"=="3" goto launch_client_only
if "%choice%"=="4" goto start_controller

:play_all_in_one
tasklist /fi "imagename eq RosRedemptionBrandingSuite.exe" 2>nul | find /i "RosRedemptionBrandingSuite.exe" >nul || start "" "%BASE_DIR%\RosRedemptionBrandingSuite.exe"
set "ROS_GAME_DIR=%BASE_DIR%"
set "ROS_RT_KEY=f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "PYTHONDONTWRITEBYTECODE=1"
if exist "%BASE_DIR%\runtime\app\start_game.pyc" (
    cd /d "%BASE_DIR%\runtime\app"
    start "" "http://127.0.0.1:8888"
    start "ROS Redemption Web Controller" "%BASE_DIR%\RosRedemptionController.exe" 8888
    "..\python\python.exe" "start_game.pyc" --direct --account Admin_Redemption
) else (
    cd /d "C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app"
    start "" "http://127.0.0.1:8888"
    start "ROS Redemption Web Controller" "%BASE_DIR%\RosRedemptionController.exe" 8888
    "..\python\python.exe" "start_game.pyc" --direct --account Admin_Redemption
)
goto end

:start_server_only
set "ROS_GAME_DIR=%BASE_DIR%"
set "ROS_RT_KEY=f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "PYTHONDONTWRITEBYTECODE=1"
if exist "%BASE_DIR%\runtime\app\start_game.pyc" (
    cd /d "%BASE_DIR%\runtime\app"
    "..\python\python.exe" "start_game.pyc" --server-only
) else (
    cd /d "C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app"
    "..\python\python.exe" "start_game.pyc" --server-only
)
goto end

:launch_client_only
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
goto end

:start_controller
start "" "http://127.0.0.1:8888"
cd /d "%BASE_DIR%"
"RosRedemptionController.exe" 8888
goto end

:end
