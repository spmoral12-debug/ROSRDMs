import os

for root, dirs, files in os.walk(r'C:\DieHardROS'):
    for f in files:
        if f.endswith('.npk'):
            p = os.path.join(root, f)
            print("NPK file:", p, os.path.getsize(p))

