with open(r'C:\DieHardROS\local_update\logs\screen_code.json', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

print("Length of screen_code.json:", len(text))
for line in text.splitlines():
    if any(k in line.lower() for k in ['login', 'logo', 'loading', 'layer_swing']):
        print(line[:120])

