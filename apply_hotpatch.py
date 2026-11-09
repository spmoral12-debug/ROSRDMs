import os, glob, zlib as zl, hashlib as hh, base64 as b64, shutil, sqlite3, json

K = bytes.fromhex('2a8ec34ed7c4baa57c7b5e4adef0f454f8f854d809daa14616db06b2eac10809')

# A. Patch unpacked_lobby.py
unpacked_path = r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py'
if os.path.exists(unpacked_path):
    with open(unpacked_path, 'r', encoding='utf-8', errors='ignore') as f:
        src = f.read()

    for old, new in [
        ("'ros.skygame.io'", "'ROS REDEMPTION'"),
        ('"ros.skygame.io"', '"ROS REDEMPTION"'),
        ('ros.skygame.io', 'ROS REDEMPTION'),
        ('DieHard ROS Online', 'ROS Redemption'),
        ('DieHard ROS', 'ROS Redemption'),
        ('DieHard', 'ROS Redemption'),
        ('diehard', 'ros_redemption'),
        ('SkyGame', 'ROS Redemption')
    ]:
        src = src.replace(old, new)

    # Disable text overwriting ticks
    idx = src.find('def _dh_brand_tick(')
    if idx >= 0:
        end_idx = src.find('\ndef ', idx + 10)
        if end_idx >= 0:
            src = src[:idx] + "def _dh_brand_tick(*args, **kwargs):\n    return\n\n" + src[end_idx+1:]

    idx = src.find('def _dh_screen_rewrite(')
    if idx >= 0:
        end_idx = src.find('\ndef ', idx + 10)
        if end_idx >= 0:
            src = src[:idx] + "def _dh_screen_rewrite(*args, **kwargs):\n    return\n\n" + src[end_idx+1:]

    idx = src.find('def _dh_write_art(')
    if idx >= 0:
        end_idx = src.find('\ndef ', idx + 10)
        if end_idx >= 0:
            new_art = "def _dh_write_art(*args, **kwargs):\n    folder = _dh_art_dir()\n    for name in ['dh_bg1.jpg', 'dh_bg2.jpg', 'dh_bg3.jpg', 'dh_bg4.jpg', 'dh_fireteam.jpg', 'dh_ev_06632.jpg', 'dh_ev_13933.jpg', 'dh_logo_1.png', 'dh_logo_2.png', 'dh_logo_3.png', 'dh_logo_4.png', 'dh_logo_5.png', 'dh_logo_sg_cloud.png', 'dh_logo_sg_cosmic.png', 'dh_qr.png']:\n        _dh_art['paths'][name] = _dh_os.path.join(folder, name)\n    return\n\n"
            src = src[:idx] + new_art + src[end_idx+1:]

    with open(unpacked_path, 'w', encoding='utf-8') as f:
        f.write(src)
    print(">>> unpacked_lobby.py: Patched cleanly!")

    # Re-encrypt payload
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

    # Overwrite updates in AppData
    for p in glob.glob(r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\hot-lobby-*.py'):
        with open(p, 'r', encoding='utf-8') as f:
            orig = f.read()
        s = orig.find('_B = [')
        e = orig.find(']\n\n', s)
        if s >= 0 and e >= 0:
            with open(p, 'w', encoding='utf-8') as f:
                f.write(orig[:s] + b_payload + orig[e+3:])
            print(">>> AppData hook updated:", os.path.basename(p))

    # Overwrite remote-lobby in C:\DieHardROS
    remote_p = r'C:\DieHardROS\local_update\hot\remote-lobby.py'
    if os.path.exists(remote_p):
        with open(remote_p, 'r', encoding='utf-8') as f:
            orig = f.read()
        s = orig.find('_B = [')
        e = orig.find(']\n\n', s)
        if s >= 0 and e >= 0:
            with open(remote_p, 'w', encoding='utf-8') as f:
                f.write(orig[:s] + b_payload + orig[e+3:])
            print(">>> local_update remote-lobby.py updated!")

# B. Tanggalin ang 9,999,999 diamonds at ayusin ang Flag / Profile sa DB
db = r'C:\DieHardROS\local_update\server_data\accounts.db'
if os.path.exists(db):
    conn = sqlite3.connect(db)
    # Reset wallet: 500 Diamonds, 20,000 Gold
    conn.execute('UPDATE wallets SET freeYuanbao = 500, payYuanbao = 0, gp = 20000')
    print(">>> Wallets reset: Tinanggal na ang 9,999,999 diamonds!")

    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(characters)")
        cols = [c[1] for c in cur.fetchall()]
        if 'country' in cols: conn.execute("UPDATE characters SET country = 'PH'")
        if 'nation' in cols: conn.execute("UPDATE characters SET nation = 'PH'")
        if 'flag' in cols: conn.execute("UPDATE characters SET flag = 'PH'")
        print(">>> Profile flag: Set to Philippines (PH)!")
    except Exception as e:
        print("Notice:", e)
    conn.commit()
    conn.close()

print("\n>>> PYTHON PATCH COMPLETE! <<<")
