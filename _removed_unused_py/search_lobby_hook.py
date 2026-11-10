with open(r'C:\DieHardROS\runtime\app\client\lobby_hook.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

print("Total lines in lobby_hook.py:", len(lines))
for idx, line in enumerate(lines):
    if any(k in line.lower() for k in ['skygame', 'ros legacy', 'layer_swing', 'txt_logo', 'dh_brand']):
        print(f"{idx+1}: {line.strip()[:100]}")

