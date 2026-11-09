import os

p = r'C:\DieHardROS\local_update\logs'
if os.path.exists(p):
    for f in os.listdir(p):
        print(f, os.path.getsize(os.path.join(p, f)))
else:
    print("Does not exist:", p)

