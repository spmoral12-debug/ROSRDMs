import os

for root, dirs, files in os.walk(r'C:\DieHardROS\runtime\app'):
    for f in files:
        if f.endswith('.py'):
            p = os.path.join(root, f)
            print(p)

