import os, glob

for p in glob.glob(r'C:\DieHardROS\*.py'):
    with open(p, 'rb') as f:
        c = f.read()
        if b'npk' in c.lower() or b'package' in c.lower():
            print(p)

