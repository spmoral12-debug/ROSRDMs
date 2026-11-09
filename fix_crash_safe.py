import os, glob, zlib as zl, hashlib as hh, base64 as b64

K = bytes.fromhex('2a8ec34ed7c4baa57c7b5e4adef0f454f8f854d809daa14616db06b2eac10809')

print("=== REPAIRING CRASH: REMOVING ALL ILLEGAL DELETIONS ===")

# 1. Fix unpacked_lobby.py
unpacked_p = r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py'
with open(unpacked_p, 'r', encoding='utf-8', errors='ignore') as f:
    code = f.read()

# Replace any removeFromParent with safe hiding
safe_replacement = """                    try:
                        node.setVisible(False)
                        if hasattr(node, 'setOpacity'): node.setOpacity(0)
                        if hasattr(node, 'setPosition'): node.setPosition(-99999, -99999)
                        if hasattr(node, 'setScale'): node.setScale(0.0001)
                    except Exception:
                        pass"""

# Let's inspect where removeFromParent appears in unpacked_lobby.py
lines = code.splitlines()
new_lines = []
for line in lines:
    if 'removeFromParent' in line:
        indent = len(line) - len(line.lstrip())
        pad = ' ' * indent
        new_lines.append(pad + "if hasattr(node, 'setOpacity'): node.setOpacity(0)")
    else:
        new_lines.append(line)

code = '\n'.join(new_lines)

with open(unpacked_p, 'w', encoding='utf-8') as f:
    f.write(code)
print("unpacked_lobby.py sanitized (no removeFromParent).")

# Re-encrypt master patch payload
print("Re-encrypting payload...")
compressed = zl.compress(code.encode('utf-8'), 9)
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
    with open(p, 'r', encoding='utf-8') as f:
        orig = f.read()
    s = orig.find('_B = [')
    e = orig.find(']\n\n', s)
    if s >= 0 and e >= 0:
        with open(p, 'w', encoding='utf-8') as f:
            f.write(orig[:s] + b_payload + orig[e+3:])
        print("Hook update written:", os.path.basename(p))

remote_p = r'C:\DieHardROS\local_update\hot\remote-lobby.py'
if os.path.exists(remote_p):
    with open(remote_p, 'r', encoding='utf-8') as f:
        orig = f.read()
    s = orig.find('_B = [')
    e = orig.find(']\n\n', s)
    if s >= 0 and e >= 0:
        with open(remote_p, 'w', encoding='utf-8') as f:
            f.write(orig[:s] + b_payload + orig[e+3:])
        print("local_update remote-lobby.py updated.")

# 2. Fix lobby_hook.py in both places
hook_targets = [
    r'C:\DieHardROS\runtime\app\client\lobby_hook.py',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app\client\lobby_hook.py'
]

for p in hook_targets:
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8', errors='ignore') as f:
            h_lines = f.readlines()
        cleaned_lines = []
        for line in h_lines:
            if 'removeFromParent' in line:
                indent = len(line) - len(line.lstrip())
                pad = ' ' * indent
                cleaned_lines.append(pad + "if hasattr(w if 'w' in dir() else node, 'setOpacity'): (w if 'w' in dir() else node).setOpacity(0)\n")
            else:
                cleaned_lines.append(line)
        with open(p, 'w', encoding='utf-8') as f:
            f.writelines(cleaned_lines)
        print("Sanitized lobby_hook.py:", p)

print("\n>>> ALL CRASH FIXES APPLIED SUCCESSFULLY! <<<")

