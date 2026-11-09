import os, glob

print("--- Searching for 'legacy' or 'ROS LEGACY' in binary/text files ---")
for root, dirs, files in os.walk(r'C:\DieHardROS'):
    # skip some huge dirs if needed
    for f in files:
        if f.lower().endswith(('.py', '.pyc', '.json', '.xml', '.txt', '.cs', '.bat', '.cmd')):
            p = os.path.join(root, f)
            try:
                with open(p, 'rb') as fp:
                    content = fp.read()
                    if b'ROS LEGACY' in content or b'ROS_LEGACY' in content or b'ros legacy' in content.lower():
                        print(f"Match in {p}")
            except Exception:
                pass

print("\n--- AppData check ---")
appdata = r'C:\Users\seanj\AppData\Local\DieHardROSHook'
if os.path.exists(appdata):
    for root, dirs, files in os.walk(appdata):
        for f in files:
            p = os.path.join(root, f)
            if f.lower().endswith(('.jpg', '.png', '.ico', '.py', '.json')):
                print(f"AppData: {p} ({os.path.getsize(p)} bytes)")

