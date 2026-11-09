import os

appdata = r'C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app'
for root, dirs, files in os.walk(appdata):
    for f in files:
        if f.endswith(('.py', '.pyc')):
            p = os.path.join(root, f)
            print(p)

