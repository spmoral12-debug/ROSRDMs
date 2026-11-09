import os, glob, zlib as zl, hashlib as hh, base64 as b64

K = bytes.fromhex('2a8ec34ed7c4baa57c7b5e4adef0f454f8f854d809daa14616db06b2eac10809')

unpacked_path = r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py'
if os.path.exists(unpacked_path):
    with open(unpacked_path, 'r', encoding='utf-8', errors='ignore') as f:
        src = f.read()

    # Fix line 3040: support setTexture on Cocos Sprites
    src = src.replace(
        "if file_path and callable(getattr(node, 'loadTexture', None)):",
        "loader = getattr(node, 'loadTexture', None) or getattr(node, 'setTexture', None)\n        if file_path and callable(loader):"
    )

    # Clean rebrand strings
    for old, rep in [
        ('ros.skygame.io', 'ROS REDEMPTION'),
        ('roslegacy.net', 'ROS REDEMPTION'),
        ('ros legacy', 'ROS Redemption'),
        ('ROS LEGACY', 'ROS REDEMPTION')
    ]:
        src = src.replace(old, rep)

    with open(unpacked_path, 'w', encoding='utf-8') as f:
        f.write(src)
    print(">>> unpacked_lobby.py: Sprite setTexture support enabled!")

    # Encrypt
    compressed = zl.compress(src.encode('utf-8'), 9)
    parts, i, c, sz = [], 0, 0, len(compressed)
    while i < sz:
        chunk = compressed[i:i+65536]
        blocks = (len(chunk)+31)//32
        ks = b''.join([hh.sha256(K + str(c+k).encode()).digest() for k in range(blocks)])[:len(chunk)]
        c += blocks
        parts.append(bytes([x^y for x,y in zip(chunk, ks)]))
        i += 65536
    encrypted = b''.join(parts)
    b64_str = b64.b64encode(encrypted).decode('ascii')
    b_lines = ['    "%s",\n' % b64_str[j:j+80] for j in range(0, len(b64_str)-80, 80)]
    rem = b64_str[len(b64_str)-(len(b64_str)%80):]
    if rem: b_lines.append('    "%s",\n' % rem)
    b_payload = '_B = [\n' + ''.join(b_lines) + ']\n\n'

    for p in glob.glob(r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\hot-lobby-*.py'):
        with open(p, 'r', encoding='utf-8') as f: orig = f.read()
        s, e = orig.find('_B = ['), orig.find(']\n\n', orig.find('_B = ['))
        if s >= 0 and e >= 0:
            with open(p, 'w', encoding='utf-8') as f: f.write(orig[:s] + b_payload + orig[e+3:])

    remote_p = r'C:\DieHardROS\local_update\hot\remote-lobby.py'
    if os.path.exists(remote_p):
        with open(remote_p, 'r', encoding='utf-8') as f: orig = f.read()
        s, e = orig.find('_B = ['), orig.find(']\n\n', orig.find('_B = ['))
        if s >= 0 and e >= 0:
            with open(remote_p, 'w', encoding='utf-8') as f: f.write(orig[:s] + b_payload + orig[e+3:])

print(">>> ALL HOOKS UPDATED!")
