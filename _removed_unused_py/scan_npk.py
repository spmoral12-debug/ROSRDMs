import re

npk = r"C:\DieHardROS\res\ui.npk"
print(">>> Ini-scan ang ui.npk...")
with open(npk, "rb") as f:
    # Read chunk
    data = f.read(50 * 1024 * 1024) # first 50MB has string table or file index

matches = set(re.findall(rb'[a-zA-Z0-9_\/\\-]+\.(?:png|jpg)', data))
found = []
for m in matches:
    try:
        s = m.decode('ascii').replace('\\', '/')
        if any(k in s.lower() for k in ['logo_zjzc', 'zjzc_wz', 'bg_loading', 'login_logo', 'img_login']):
            found.append(s)
    except:
        pass

print(">>> NATAGPUANG EXACT INTERNAL PATHS SA UI.NPK:")
for p in sorted(found):
    print("   ", p)
