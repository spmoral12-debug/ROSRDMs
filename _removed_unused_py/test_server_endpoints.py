import urllib.request
import json
import time
import subprocess
import os

# Start launcher_server in background
python_exe = r"C:\DieHardROS\runtime\python\python.exe"
server_py = r"C:\DieHardROS\launcher\launcher_server.py"

p = subprocess.Popen([python_exe, server_py], cwd=r"C:\DieHardROS")
time.sleep(1.5)

urls = [
    "http://127.0.0.1:8799/",
    "http://127.0.0.1:8799/admin",
    "http://127.0.0.1:8799/api/status",
    "http://127.0.0.1:8799/api/accounts",
    "http://127.0.0.1:8799/api/admin/overview",
    "http://127.0.0.1:8799/api/admin/players",
    "http://127.0.0.1:8799/api/admin/hwids"
]

all_ok = True
for u in urls:
    try:
        req = urllib.request.urlopen(u, timeout=2)
        status = req.getcode()
        body = req.read()
        print(f"[OK] {u} -> Status {status}, Length {len(body)}")
    except Exception as e:
        print(f"[FAIL] {u} -> {e}")
        all_ok = False

p.terminate()
p.wait()

print("Test complete. Success:", all_ok)

