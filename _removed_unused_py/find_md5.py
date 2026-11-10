import os, glob, hashlib

def md5(p):
    with open(p, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

target_md5 = 'cc522252ab57e5b47f441da71f1510a6'
brain = r'C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a'

for root, dirs, files in os.walk(brain):
    for f in files:
        p = os.path.join(root, f)
        try:
            if md5(p) == target_md5:
                print("MATCH FOUND IN BRAIN:", p)
        except Exception:
            pass

