import os

for path in [
    r'C:\DieHardROS\local_update\logs\screen_UILogin.json',
    r'C:\DieHardROS\runtime\app\local_update\logs\screen_UILogin.json',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\local_update\logs\screen_UILogin.json'
]:
    if os.path.exists(path):
        print("Found:", path, os.path.getsize(path))

