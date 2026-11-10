import os, glob

print("Scanning for all .npk and .json and .xml files for 'txt_logo' or 'legacy'...")
for root, dirs, files in os.walk(r'C:\DieHardROS'):
    for f in files:
        if f.lower().endswith(('.json', '.xml', '.plist')):
            p = os.path.join(root, f)
            try:
                with open(p, 'rb') as fp:
                    content = fp.read()
                    if b'txt_logo' in content or b'legacy' in content.lower():
                        print(f"Match in {p}")
            except Exception:
                pass

