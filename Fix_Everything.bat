@echo off
title ROS REDEMPTION - ALL-IN-ONE FIX
color 0C

echo ================================================================
echo   PINAPATAY ANG LAHAT NG LUMANG PROSESO AT ASUL NA CONTROLLER...
echo ================================================================
taskkill /F /T /IM ros64.exe 2>nul
taskkill /F /T /IM python.exe 2>nul
taskkill /F /T /IM IconInjector.exe 2>nul
timeout /t 1 /nobreak >nul

attrib -r "C:\DieHardROS\Documents\res\dh_brand\*.*" /s 2>nul
attrib -r "C:\DieHardROS\runtime\app\*.*" 2>nul

set PY="C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\python\python.exe"

%PY% "C:\DieHardROS\run_all_fixes.py"

echo.
echo ================================================================
echo   TAPOS NA! BINUBUKSAN NA ANG ROS REDEMPTION...
echo ================================================================
call "C:\DieHardROS\Play_ROS_Redemption.bat"
