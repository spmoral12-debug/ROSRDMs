import os, hashlib

brain = r'C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a'

def md5(p):
    with open(p, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

md5s = {
    '4092a74521f44a3f3b93ba4614134248': 'bg_loading_01.png',
    '516aa828262109530e17edf8a05262aa': 'dh_rank_s1.jpg',
    'b21dee8628fd0ce2f03386b2dde9ad76': 'dh_bg1.jpg',
    'cc522252ab57e5b47f441da71f1510a6': 'txt_logo_zjzc.png'
}

for root, dirs, files in os.walk(brain):
    for f in files:
        if f.lower().endswith(('.jpg', '.png')):
            p = os.path.join(root, f)
            h = md5(p)
            if h in md5s:
                print(f"MATCH: {md5s[h]} <===> {p}")
            else:
                # also print base name
                print(f"Other brain file: {f} ({os.path.getsize(p)} bytes) md5={h[:10]}")

