import zlib, base64

with open(r'C:\DieHardROS\local_update\hot\remote-lobby.py', 'rb') as f:
    text = f.read().decode('utf-8')

lines = text.splitlines()
B = []
in_B = False
for line in lines:
    if '_B = [' in line:
        in_B = True
        continue
    if in_B:
        if line.strip() == ']':
            break
        B.append(line.strip().strip('",'))

key = bytes.fromhex('2a8ec34ed7c4baa57c7b5e4adef0f454f8f854d809daa14616db06b2eac10809')
def _r(b, k):
    d = base64.b64decode(b)
    n = len(k)
    return bytes(bytearray(d[i] ^ k[i % n] for i in range(len(d))))

raw = b''.join(_r(c, key) for c in B)
decomp = zlib.decompress(raw)
print('Successfully decrypted remote-lobby.py!')
print('Decompressed size:', len(decomp))
compile(decomp, 'lobby_hot_patch', 'exec')
print('Syntax check PASSED!')

