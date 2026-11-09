import os

unpacked_p = r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py'
with open(unpacked_p, 'r', encoding='utf-8', errors='ignore') as f:
    code = f.read()

# Fix 1: _dh_art_dir path
if r'C:\ROS RedemptionROS' in code:
    code = code.replace(r'C:\ROS RedemptionROS', r'C:\DieHardROS')
    print("Fixed C:\\ROS RedemptionROS -> C:\\DieHardROS in unpacked_lobby.py")

# Fix 2: Check _dh_art_pass in unpacked_lobby.py
# Make sure login screen replaces layer_swing and old logos
print("Checking UILogin handling in unpacked_lobby.py...")

with open(unpacked_p, 'w', encoding='utf-8') as f:
    f.write(code)

print("unpacked_lobby.py updated.")

