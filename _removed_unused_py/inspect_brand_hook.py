with open(r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if 'the login loop' in line or '_dh_is_logo_file' in line:
        start = max(0, idx - 40)
        end = min(len(lines), idx + 60)
        print(f"=== Found at line {idx} ===")
        for j in range(start, end):
            print(f"{j+1}: {lines[j]}", end='')
        break

