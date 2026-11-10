import os

unpacked_p = r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py'
with open(unpacked_p, 'r', encoding='utf-8', errors='ignore') as f:
    src = f.read()

print("Does unpacked_lobby have _dh_apply_screen_branding?", '_dh_apply_screen_branding' in src)

