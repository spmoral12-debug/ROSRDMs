import os, sys

target1 = b"Please contact us"
target2 = b"ros.skygame.io"

print("================================================================")
print(">>> SINUSURI KUNG SAANG FILE NAKABAON ANG SNIPER LOADING SCREEN...")
print("================================================================")

found_files = []
for root, dirs, files in os.walk(r"C:\DieHardROS"):
    for f in files:
        # I-check ang lahat ng NPK, PYC, DAT, at configs
        if f.lower().endswith(('.npk', '.pyc', '.dat', '.json', '.xml', '.txt', '.bin', '.pak')):
            p = os.path.join(root, f)
            try:
                with open(p, "rb") as fp:
                    data = fp.read()
                    if target1 in data or target2 in data:
                        print(f"  [NAKITA DITO!] -> {p}")
                        found_files.append(p)
            except:
                pass

print("\n>>> MGA NAKITANG MALALAKING WALLPAPERS / IMAGES:")
for root, dirs, files in os.walk(r"C:\DieHardROS"):
    for f in files:
        if f.lower().endswith(('.jpg', '.png', '.dds', '.tga')):
            p = os.path.join(root, f)
            try:
                sz = os.path.getsize(p)
                if sz > 100 * 1024: # Malalaking wallpapers (100KB pataas)
                    print(f"  IMAGE ({sz//1024} KB): {p}")
            except:
                pass
print("\n>>> TAPOS NA ANG SCAN!")
