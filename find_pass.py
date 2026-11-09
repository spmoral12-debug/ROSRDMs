with open(r"C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py", "r", encoding="utf-8", errors="ignore") as f:
    for idx, line in enumerate(f):
        if "def _dh_scene_brand_pass" in line:
            print(f"FOUND AT LINE {idx+1}")
