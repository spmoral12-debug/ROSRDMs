with open(r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if '_dh_art_pass' in line:
        print(f"Line {idx+1}: {line}")

