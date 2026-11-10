with open(r'C:\DieHardROS\runtime\app\client\lobby_hook.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if 'def walk_ui_nodes' in line:
        for j in range(idx, min(len(lines), idx + 35)):
            print(f"{j+1}: {lines[j]}", end='')
        break

