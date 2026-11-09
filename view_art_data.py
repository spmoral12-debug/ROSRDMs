with open(r"C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

for i in range(8360, min(8390, len(lines))):
    print(f"Line {i+1}: {lines[i][:100]}")
