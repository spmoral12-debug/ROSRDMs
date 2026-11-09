with open(r"C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

for i in range(2670, min(2720, len(lines))):
    print(f"Line {i+1}: {lines[i].strip()[:100]}")
