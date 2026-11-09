import os
import sys
import rrboot

rrboot.install()
out_dir = r"c:\Users\seanj\dev\server_extracted"
os.makedirs(out_dir, exist_ok=True)

print(f"Extracting {len(rrboot._files)} files to {out_dir}...")
for rel_path in rrboot._files.keys():
    data = rrboot.read(rel_path)
    if data is None:
        continue
    target_path = os.path.join(out_dir, rel_path)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with open(target_path, "wb") as f:
        f.write(data)
    print(f"Extracted: {rel_path} ({len(data)} bytes)")

print("Done extraction!")
