import os, sys

target1 = b"Please contact us"
target2 = b"ros.skygame.io"

print("Scanning for targets in non-NPK files...")
for root, dirs, files in os.walk(r"C:\DieHardROS"):
    for f in files:
        if f.lower().endswith(('.pyc', '.py', '.dat', '.json', '.xml', '.txt', '.bin', '.pak')):
            p = os.path.join(root, f)
            try:
                with open(p, "rb") as fp:
                    data = fp.read()
                    if target1 in data or target2 in data:
                        print(f"  [FOUND!] -> {p}")
            except:
                pass

