import os

p = r'C:\DieHardROS\ccmini'
if os.path.exists(p):
    for f in os.listdir(p):
        print(f, os.path.getsize(os.path.join(p, f)))

