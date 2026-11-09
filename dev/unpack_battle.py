import base64, hashlib, zlib, re

with open(r'C:\DieHardROS\local_update\hot\remote-battle.py', 'r', encoding='utf-8') as f:
    text = f.read()

m_key = re.search(r'_K = "([0-9a-fA-F]+)"', text)
key_bytes = bytes.fromhex(m_key.group(1))

m_b = re.findall(r'"([A-Za-z0-9+/=]+)",', text)
raw = base64.b64decode(''.join(m_b))

parts = []
i = 0
c = 0
size = len(raw)
while i < size:
    chunk = raw[i:i + 65536]
    blocks = (len(chunk) + 31) // 32
    ks = b''.join([hashlib.sha256(key_bytes + str(c + k).encode('ascii')).digest() for k in range(blocks)])[:len(chunk)]
    c += blocks
    xored = bytes(bytearray(a ^ b for a, b in zip(chunk, ks)))
    parts.append(xored)
    i += 65536

src = zlib.decompress(b''.join(parts))
print('Successfully decrypted remote-battle.py! Size:', len(src))
with open(r'c:\Users\seanj\dev\unpacked_battle.py', 'wb') as f:
    f.write(src)
print('Saved to c:\\Users\\seanj\\dev\\unpacked_battle.py')

