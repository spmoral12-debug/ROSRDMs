import zlib, base64

with open(r'C:\DieHardROS\local_update\hot\remote-battle.py', 'rb') as f:
    src = f.read().decode('utf-8')

B = []
in_B = False
for line in src.splitlines():
    if '_B = [' in line:
        in_B = True
        continue
    if in_B:
        if line.strip() == ']':
            break
        B.append(line.strip().strip('",'))

key_hex = 'a29631e24ba664471e72043de2cb8bcbf85de0000a1fcb5a345ec289b10b9287'
k = bytes.fromhex(key_hex)
def _r(b, k):
    d = base64.b64decode(b)
    n = len(k)
    return bytes(bytearray(d[i] ^ k[i % n] for i in range(len(d))))

raw = b''.join(_r(c, k) for c in B)
decomp = zlib.decompress(raw)
print('Decompressed remote-battle.py size:', len(decomp))
if b'hot-patch-rejected' in decomp:
    print('Found hot-patch-rejected in remote-battle.py!')
    idx = decomp.find(b'hot-patch-rejected')
    print(decomp[idx-100:idx+300].decode('utf-8', errors='replace'))

