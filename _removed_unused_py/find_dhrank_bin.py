import os

for root, dirs, files in os.walk(r'C:\DieHardROS'):
    for f in files:
        if f.lower().endswith(('.dll', '.exe', '.npk', '.dat')):
            p = os.path.join(root, f)
            try:
                with open(p, 'rb') as fp:
                    content = fp.read()
                    if b'dh_rank' in content:
                        print(f"Match in {p}")
            except Exception:
                pass

