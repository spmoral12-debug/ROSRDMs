import os, hashlib

for path in [
    r'C:\DieHardROS\Documents\res\txt_logo_zjzc.png',
    r'C:\DieHardROS\x64\Documents\res\txt_logo_zjzc.png',
    r'C:\DieHardROS\runtime\Documents\res\txt_logo_zjzc.png',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\Documents\res\txt_logo_zjzc.png'
]:
    if os.path.exists(path):
        size = os.path.getsize(path)
        with open(path, 'rb') as f:
            h = hashlib.md5(f.read()).hexdigest()
        print(f"{path}: size={size}, md5={h}")

