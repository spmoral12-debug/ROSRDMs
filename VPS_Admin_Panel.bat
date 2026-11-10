@echo off
title ROS Redemption - VPS Admin Tunnel
color 0B
echo ====================================================
echo   ROS REDEMPTION - PRIVATE VPS ADMIN TUNNEL (SSH)
echo ====================================================
echo.
echo Opening http://127.0.0.1:8790/admin in your browser...
echo Enter your VPS root password below when prompted!
echo Keep this window open while using the Admin Panel.
echo.
start "" "http://127.0.0.1:8790/admin?key=wYq5VSkn6wgUschxPBxu51z1ZolmgbKt"
ssh -p 30060 -L 8790:127.0.0.1:8790 root@143.14.88.9
pause
