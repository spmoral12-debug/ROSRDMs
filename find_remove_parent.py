import os

target = 'removeFromParent'
for root, dirs, files in os.walk(r'C:\DieHardROS'):
    for f in files:
        if f.endswith('.py'):
            p = os.path.join(root, f)
            with open(p, 'r', encoding='utf-8', errors='ignore') as fp:
                c = fp.read()
                if target in c:
                    print(f"Match in {p}")

for root, dirs, files in os.walk(r'C:\Users\seanj\AppData\Local\DieHardROSHook'):
    for f in files:
        if f.endswith('.py'):
            p = os.path.join(root, f)
            with open(p, 'r', encoding='utf-8', errors='ignore') as fp:
                c = fp.read()
                if target in c:
                    print(f"Match in AppData: {p}")

