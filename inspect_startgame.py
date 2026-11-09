import os

with open(r'C:\DieHardROS\runtime\app\start_game.pyc', 'rb') as f:
    data = f.read()

import re
strings = re.findall(rb'[A-Za-z0-9_\-\.\:\/ ]{4,}', data)
for s in strings:
    s_str = s.decode('latin1', errors='ignore')
    if any(k in s_str.lower() for k in ['legacy', 'logo', 'splash', 'ccmini', 'title', 'brand']):
        print(s_str)

