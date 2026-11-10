import re

with open(r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

classes = re.findall(r'class\s+([A-Za-z0-9_]*Login[A-Za-z0-9_]*)\b', content)
print("Login classes:", set(classes))

for line in content.splitlines():
    if any(k in line for k in ['layer_swing', 'txt_logo_zjzc', 'dh_brand', 'ROS-Redemption', 'ROS LEGACY']):
        print(line[:120])

