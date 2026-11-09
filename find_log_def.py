with open(r"C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py", "r", encoding="utf-8", errors="ignore") as f:
    for idx, line in enumerate(f):
        if "def log(" in line or "def log_error(" in line:
            print(f"Line {idx+1}: {line.strip()}")
            # Print next 10 lines
            for _ in range(10):
                print("   ", next(f, "").strip())
            break
