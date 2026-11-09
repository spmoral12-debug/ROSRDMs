with open(r"C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py", "r", encoding="utf-8", errors="ignore") as f:
    for idx, line in enumerate(f):
        if "_DH_BRAND_ASSETS" in line and idx != 8361:
            print(f"Line {idx+1}: {line.strip()[:100]}")
