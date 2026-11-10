import os

print(">>> NAG-I-SCAN SA BUONG C:\\DieHardROS PARA SA 'skygame.io'...")
target = b"skygame.io"
found = []

for root, dirs, files in os.walk(r"C:\DieHardROS"):
    for f in files:
        # Laktawan ang sarili nating script at logs
        if f.endswith((".log", ".py", ".pyc", ".ico")):
            continue
        p = os.path.join(root, f)
        try:
            with open(p, "rb") as fp:
                data = fp.read()
                if target in data:
                    found.append((p, len(data)))
        except:
            pass

print("\n>>> NATAGPUAN SA MGA SUMUSUNOD NA FILES:")
for p, sz in found:
    print(f"   [{sz} bytes] -> {p}")
if not found:
    print("   (Walang file sa C:\\DieHardROS na may direct skygame.io text!)")
