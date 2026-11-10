with open(r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if 'def _dh_screen_rewrite' in line:
        for j in range(idx, min(len(lines), idx + 60)):
            print(f"{j+1}: {lines[j]}", end='')
        break

