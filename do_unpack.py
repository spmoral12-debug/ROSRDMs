import base64, zlib, hashlib, re

def unpack_hot_patch(filepath, key_hex):
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    s = text.find('_B = [')
    e = text.find(']\n', s)
    if e == -1:
        e = text.find(']\r\n', s)
    b_lines = text[s+6:e].strip().splitlines()
    b64_str = ''.join([line.strip().strip('",') for line in b_lines])
    raw = base64.b64decode(b64_str)
    k = bytes.fromhex(key_hex)
    parts = []
    i = 0
    c = 0
    size = len(raw)
    while i < size:
        chunk = raw[i:i + 65536]
        blocks = (len(chunk) + 31) // 32
        ks = b''.join([hashlib.sha256(k + str(c + m).encode('ascii')).digest() for m in range(blocks)])[:len(chunk)]
        c += blocks
        xored = bytes(bytearray(a ^ b for a, b in zip(chunk, ks)))
        parts.append(xored)
        i += 65536
    return zlib.decompress(b''.join(parts))

battle_key = 'a29631e24ba664471e72043de2cb8bcbf85de0000a1fcb5a345ec289b10b9287'
lobby_key = '2a8ec34ed7c4baa57c7b5e4adef0f454f8f854d809daa14616db06b2eac10809'

battle_src = unpack_hot_patch(r'C:\DieHardROS\local_update\hot\remote-battle.py', battle_key)
print('Decrypted remote-battle.py:', len(battle_src))
with open(r'c:\Users\seanj\dev\clean_remote_battle.py', 'wb') as f:
    f.write(battle_src)

lobby_src = unpack_hot_patch(r'C:\DieHardROS\local_update\hot\remote-lobby.py', lobby_key)
print('Decrypted remote-lobby.py:', len(lobby_src))
with open(r'c:\Users\seanj\dev\clean_remote_lobby.py', 'wb') as f:
    f.write(lobby_src)

print('Done unpacking!')

