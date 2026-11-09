import os, subprocess

p = r'C:\DieHardROS\runtime\app\start_game.pyc'
print("start_game.pyc exists:", os.path.exists(p))

bat = r'C:\DieHardROS\Play_ROS_Redemption.bat'
with open(bat, 'r') as f:
    print(f.read())

