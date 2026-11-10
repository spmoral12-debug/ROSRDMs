import zlib, base64, glob, hashlib

key = bytes.fromhex('2a8ec34ed7c4baa57c7b5e4adef0f454f8f854d809daa14616db06b2eac10809')

paths = [
    r'local_update\hot\remote-lobby.py',
    r'C:\DieHardROS\ROS-REDEMPTION\DieHardROS\local_update\hot\remote-lobby.py',
    r'ROS_Redemption_Server_Package\local_update\hot\remote-lobby.py'
]

for path in paths:
    with open(path, 'rb') as f:
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
    
    # Keystream decrypt
    raw = base64.b64decode(''.join(B))
    parts = []
    i = 0
    c = 0
    size = len(raw)
    while i < size:
        chunk = raw[i:i + 65536]
        blocks = (len(chunk) + 31) // 32
        ks = b''.join([hashlib.sha256(key + str(c + k).encode('ascii')).digest() for k in range(blocks)])[:len(chunk)]
        c += blocks
        xored = bytes(bytearray(a ^ b for a, b in zip(chunk, ks)))
        parts.append(xored)
        i += 65536
    
    decomp = zlib.decompress(b''.join(parts))
    print(path, 'decompressed size:', len(decomp))
    compile(decomp, 'lobby_hot_patch', 'exec')
    print(path, 'COMPILED SUCCESSFULLY!')

print('ALL LOBBY PATCHES VERIFIED 100% OK!')
