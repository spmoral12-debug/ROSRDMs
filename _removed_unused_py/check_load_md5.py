import os, hashlib

def md5(p):
    with open(p, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

p1 = r'C:\DieHardROS\Documents\res\ui\images\loading\bg_loading_01.png'
p2 = r'C:\DieHardROS\Documents\res\dh_brand\dh_rank_s1.jpg'
p3 = r'C:\DieHardROS\Documents\res\dh_brand\dh_bg1.jpg'

for p in [p1, p2, p3]:
    if os.path.exists(p):
        print(f"{p}: size={os.path.getsize(p)}, md5={md5(p)}")

