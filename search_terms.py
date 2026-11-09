import os

search_terms = ['could not be entered', 'battle entry failed', 'step 0', 'The battleground']
files = [
    r'c:\Users\seanj\dev\unpacked_hot_battle.py',
    r'c:\Users\seanj\dev\clean_remote_battle.py',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py'
]

for f in files:
    if os.path.exists(f):
        with open(f, 'r', encoding='utf-8', errors='ignore') as fp:
            content = fp.read()
            for t in search_terms:
                if t in content:
                    print(f"Found '{t}' in {f}")

