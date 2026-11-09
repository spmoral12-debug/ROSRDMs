import os

for root in [r'C:\DieHardROS', r'C:\DieHardROS\x64', r'C:\DieHardROS\runtime', r'C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25']:
    p = os.path.join(root, 'Documents', 'res', 'dh_brand')
    print(f"Exists {p}: {os.path.exists(p)}")
    if os.path.exists(p):
        print("  files:", len(os.listdir(p)))

