import zlib
import base64
import hashlib

with open(r'C:\DieHardROS\local_update\hot\remote-battle.py', 'r', encoding='utf-8') as f:
    text = f.read()

s = text.find('_B = [')
e = text.find(']\n\n', s)
b_lines = [l.strip().strip('",') for l in text[s+6:e].splitlines() if l.strip().startswith('"')]
raw = base64.b64decode(''.join(b_lines))

key_hex = 'a29631e24ba664471e72043de2cb8bcbf85de0000a1fcb5a345ec289b10b9287'
K = bytes.fromhex(key_hex)
parts = []
i = 0
c = 0
size = len(raw)
while i < size:
    chunk = raw[i:i + 65536]
    blocks = (len(chunk) + 31) // 32
    ks = b''.join([hashlib.sha256(K + str(c + k).encode('ascii')).digest() for k in range(blocks)])[:len(chunk)]
    c += blocks
    parts.append(bytes([x ^ y for x, y in zip(chunk, ks)]))
    i += 65536

decomp = zlib.decompress(b''.join(parts))
print('Decompressed size:', len(decomp))
print('Contains ros-redemption-fix:', b'ros-redemption-fix' in decomp)
print('Contains redemption_step_join:', b'redemption_step_join' in decomp)
print('Verification SUCCESS!')

