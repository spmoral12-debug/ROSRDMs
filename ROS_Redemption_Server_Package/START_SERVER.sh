#!/bin/bash
# ===================================================================
#             ROS REDEMPTION - DEDICATED LINUX SERVER LAUNCHER
# ===================================================================

cd "$(dirname "$0")"

echo "==================================================================="
echo "            ROS REDEMPTION - DEDICATED MASTER SERVER"
echo "==================================================================="
echo "  Lobby / Game Port  : 19000 (TCP / UDP)"
echo "  Battleground Port  : 19100 (UDP)"
echo "  Admin Dashboard    : http://0.0.0.0:8790/admin"
echo "  Update Mirror      : Ports 80 / 443"
echo "==================================================================="
echo ""

export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# Check python3 is installed
if command -v python3 &> /dev/null; then
    exec python3 run_server.py "$@"
elif command -v python &> /dev/null; then
    exec python run_server.py "$@"
else
    echo "[ERROR] Python 3 is not installed. Run: sudo apt update && sudo apt install -y python3"
fi

