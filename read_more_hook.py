with open(r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for j in range(1535, min(len(lines), 1660)):
    print(f"{j+1}: {lines[j]}", end='')

