import zlib as zl
import hashlib as hh
import base64 as b64

p = r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\hot-battle-2026.11.02m50.py'
with open(p, 'r') as f:
    text = f.read()

s = text.find('_B = [')
e = text.find(']\n', s)
b_block = text[s:e]
lines = []
for l in b_block.splitlines():
    l = l.strip()
    if l.startswith('"'):
        # strip quote and trailing comma
        if l.endswith('",'):
            lines.append(l[1:-2])
        elif l.endswith('"'):
            lines.append(l[1:-1])

raw_b64 = ''.join(lines)
encrypted = b64.b64decode(raw_b64)

K = bytes.fromhex('a29631e24ba664471e72043de2cb8bcbf85de0000a1fcb5a345ec289b10b9287')
parts = []
i, c, sz = 0, 0, len(encrypted)
while i < sz:
    chunk = encrypted[i:i+65536]
    blocks = (len(chunk)+31)//32
    ks = b''.join([hh.sha256(K + str(c+k).encode()).digest() for k in range(blocks)])[:len(chunk)]
    c += blocks
    parts.append(bytes([x^y for x,y in zip(chunk, ks)]))
    i += 65536

decrypted = zl.decompress(b''.join(parts)).decode('utf-8')
print('Decrypted size:', len(decrypted))
with open(r'c:\Users\seanj\dev\unpacked_hot_battle.py', 'w', encoding='utf-8') as out:
    out.write(decrypted)

found = False
for line in decrypted.splitlines():
    if 'battle entry failed' in line or 'step 0' in line:
        print('Line:', line.strip())
        found = True
if not found:
    print('Not in hot-battle-2026.11.02m50.py')

