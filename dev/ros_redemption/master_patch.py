import os, glob, zlib as zl, hashlib as hh, base64 as b64, shutil, sqlite3
from PIL import Image

K = bytes.fromhex('2a8ec34ed7c4baa57c7b5e4adef0f454f8f854d809daa14616db06b2eac10809')

# 1. Read and patch the unpacked code
unpacked_path = r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py'
with open(unpacked_path, 'r', encoding='utf-8') as f:
    src = f.read()

src = src.replace("'ros.skygame.io'", "'ROS REDEMPTION'")
src = src.replace('"ros.skygame.io"', '"ROS REDEMPTION"')
src = src.replace('ros.skygame.io', 'ROS REDEMPTION')
src = src.replace('DieHard ROS Online', 'ROS Redemption')
src = src.replace('DieHard ROS', 'ROS Redemption')
src = src.replace('DieHard', 'ROS Redemption')
src = src.replace('SkyGame', 'ROS Redemption')

# Disable disk overwriting in _dh_write_art
idx = src.find('def _dh_write_art():')
if idx >= 0:
    end_idx = src.find('def _dh_art_file(name):', idx)
    new_art = "def _dh_write_art():\n    folder = _dh_art_dir()\n    for name in ['dh_bg1.jpg', 'dh_bg2.jpg', 'dh_bg3.jpg', 'dh_bg4.jpg', 'dh_fireteam.jpg', 'dh_ev_06632.jpg', 'dh_ev_13933.jpg', 'dh_logo_1.png', 'dh_logo_2.png', 'dh_logo_3.png', 'dh_logo_4.png', 'dh_logo_5.png', 'dh_logo_sg_cloud.png', 'dh_logo_sg_cosmic.png', 'dh_qr.png']:\n        _dh_art['paths'][name] = _dh_os.path.join(folder, name)\n    return\n\n\n"
    src = src[:idx] + new_art + src[end_idx:]
    print("Patched _dh_write_art: disk overwrite permanently disabled!")

# 2. Pack back into encrypted payload
print("Encrypting master hot-patch...")
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
    with open(p, 'r', encoding='utf-8') as f:
        orig = f.read()
    s = orig.find('_B = [')
    e = orig.find(']\n\n', s)
    if s >= 0 and e >= 0:
        updated = orig[:s] + b_payload + orig[e+3:]
        with open(p, 'w', encoding='utf-8') as f:
            f.write(updated)
        print("Updated patch file:", os.path.basename(p))

# 3. Install new ROS REDEMPTION images to dh_brand
dest = r'C:\DieHardROS\Documents\res\dh_brand'
os.makedirs(dest, exist_ok=True)
bg_path = r'C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_splash_clean_1794018381576.jpg'
logo_path = r'C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_title_logo_1794018691342.jpg'

for bg_file in ['dh_bg1.jpg', 'dh_bg2.jpg', 'dh_bg3.jpg', 'dh_bg4.jpg', 'dh_fireteam.jpg', 'dh_ev_06632.jpg', 'dh_ev_13933.jpg']:
    shutil.copyfile(bg_path, os.path.join(dest, bg_file))

im = Image.open(logo_path)
logo_png = os.path.join(dest, 'temp_logo.png')
im.save(logo_png, 'PNG')
for l_file in ['dh_logo_1.png', 'dh_logo_2.png', 'dh_logo_3.png', 'dh_logo_4.png', 'dh_logo_5.png', 'dh_logo_sg_cloud.png', 'dh_logo_sg_cosmic.png']:
    shutil.copyfile(logo_png, os.path.join(dest, l_file))
if os.path.exists(logo_png): os.remove(logo_png)

im_blank = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
im_blank.save(os.path.join(dest, 'dh_qr.png'), 'PNG')

# 4. Inject 9,999,999 Diamonds & Gold
db = r'C:\DieHardROS\local_update\server_data\accounts.db'
if os.path.exists(db):
    conn = sqlite3.connect(db)
    conn.execute('UPDATE wallets SET freeYuanbao = 9999999, payYuanbao = 9999999, gp = 9999999')
    conn.commit()
    conn.close()
    print(">>> 9,999,999 DIAMONDS & GOLD INJECTED! <<<")

print("\n>>> MASTER FIX 100% COMPLETE! LAUNCH YOUR GAME NOW! <<<")
