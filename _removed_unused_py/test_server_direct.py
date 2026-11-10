import urllib.request
import json
import time
import subprocess
import os

python_exe = r"C:\DieHardROS\runtime\python\python.exe"
server_py = r"C:\DieHardROS\launcher\launcher_server.py"

# Test importing launcher_server and check routes directly
import sys
sys.path.insert(0, os.path.dirname(server_py))
import launcher_server

print("ADMIN_HTML length:", len(launcher_server.ADMIN_HTML))
print("LAUNCHER_HTML length:", len(launcher_server.LAUNCHER_HTML))

# Now test starting on port 8792
launcher_server.PORT = 8792
import threading
t = threading.Thread(target=launcher_server.run_server, daemon=True)
t.start()
time.sleep(1.0)

urls = [
    "http://127.0.0.1:8792/",
    "http://127.0.0.1:8792/admin",
    "http://127.0.0.1:8792/api/status",
    "http://127.0.0.1:8792/api/accounts",
    "http://127.0.0.1:8792/api/admin/overview",
    "http://127.0.0.1:8792/api/admin/players",
    "http://127.0.0.1:8792/api/admin/hwids"
]

for u in urls:
    try:
        req = urllib.request.urlopen(u, timeout=2)
        body = req.read()
        print(f"[OK] {u} -> Status {req.getcode()}, Length {len(body)}")
    except Exception as e:
        print(f"[FAIL] {u} -> {e}")

