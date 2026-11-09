import os

p = r'C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_tactical_sniper_clean_1794047799428.jpg'
with open(p, 'rb') as f:
    data = f.read()

import re
print("Strings in sniper clean:", re.findall(rb'[A-Za-z0-9_\-\.]{5,}', data[:2000]))
print("Contains skygame?", b'skygame' in data.lower())
print("Contains diehard?", b'diehard' in data.lower())
print("Contains legacy?", b'legacy' in data.lower())

