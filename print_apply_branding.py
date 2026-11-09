with open(r'C:\DieHardROS\runtime\app\client\lobby_hook.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for j in range(13130, len(lines)):
    print(f"{j+1}: {lines[j]}", end='')

