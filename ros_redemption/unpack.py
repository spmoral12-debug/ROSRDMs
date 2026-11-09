import base64 as b64, hashlib as hh, zlib as zl

with open(r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\hot-lobby-2026.11.06m134.py', 'r') as f:
    text = f.read()

K = bytes.fromhex('2a8ec34ed7c4baa57c7b5e4adef0f454f8f854d809daa14616db06b2eac10809')
s = text.find('_B = [')
e = text.find(']\n\n', s)
raw = b64.b64decode(''.join([l.strip()[1:-2] for l in text[s+6:e].strip().split('\n') if l.strip().startswith('"')]))

parts, i, c, sz = [], 0, 0, len(raw)
while i < sz:
    chunk = raw[i:i+65536]
    blocks = (len(chunk)+31)//32
    ks = b''.join([hh.sha256(K + str(c+k).encode()).digest() for k in range(blocks)])[:len(chunk)]
    c += blocks
    parts.append(bytes([x^y for x,y in zip(chunk, ks)]))
    i += 65536

src = zl.decompress(b''.join(parts)).decode('utf-8', 'ignore')
out_path = r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py'
with open(out_path, 'w', encoding='utf-8') as out:
    out.write(src)

print('SUCCESS UNPACKED! Total lines:', len(src.splitlines()))
