import os

path = r"C:\DieHardROS\runtime\app\local_update\hot\server_patch.py"
try:
    with open(path, "a") as f:
        pass
    print("File is NOT locked!")
except Exception as e:
    print("File lock error:", e)

