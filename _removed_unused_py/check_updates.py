import os

print(">>> 1. LAHAT NG UPDATES SA APPDATA:")
updates_dir = r"C:\Users\seanj\AppData\Local\DieHardROSHook\updates"
if os.path.exists(updates_dir):
    for f in sorted(os.listdir(updates_dir)):
        p = os.path.join(updates_dir, f)
        print(f"   {f} ({os.path.getsize(p)} bytes)")

print("\n>>> 2. FILES SA RUNTIME APP:")
app_dir = r"C:\DieHardROS\runtime\app"
if os.path.exists(app_dir):
    for f in sorted(os.listdir(app_dir)):
        p = os.path.join(app_dir, f)
        print(f"   {f} ({os.path.getsize(p)} bytes)")
