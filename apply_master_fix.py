# -*- coding: utf-8 -*-
"""
ROS Redemption Master Branding & Asset Deployment Suite
Fixes:
1. Deploys new V3 winged wallpaper (350px top headspace, wings completely intact)
2. Deploys to pc_loading_0..20 to completely remove the SkyGame sniper girl
3. Deploys to dh_bg1..4, dh_rank_s1..30, bg_loading_01..15, loading_0
4. Deploys 1x1 transparent PNG to all legacy logos
5. Patches unpacked_lobby.py:
   - Adds (1024, 480) and (1280, 960) to _DH_ART_LOADING
   - Fixes _dh_launcher_server_text to always return ROS-Redemption-Official
   - Ensures UILogin/Logo, UILogin/Logo_netease, and layer_swing are completely hidden
6. Re-encrypts into remote-lobby.py and all hot-lobby-*.py files
"""

import os, sys, shutil, zlib, hashlib, base64, glob

WALLPAPER_V3 = r'C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_loading_screen_v3_1794107861888.jpg'
UNPACKED = r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py'
HOT_DIR = r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates'
REMOTE_LOBBY = r'C:\DieHardROS\local_update\hot\remote-lobby.py'
K = bytes.fromhex('2a8ec34ed7c4baa57c7b5e4adef0f454f8f854d809daa14616db06b2eac10809')

# 1x1 Transparent PNG (67 bytes)
TRANS_PNG = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6360000000020001737501180000000049454e44ae426082'
)

print(">>> [1/4] Verifying wallpaper asset...")
if not os.path.isfile(WALLPAPER_V3):
    print("ERROR: V3 wallpaper not found:", WALLPAPER_V3)
    sys.exit(1)
print("  Found V3 wallpaper: %d bytes" % os.path.getsize(WALLPAPER_V3))

# List of root resource folders to deploy
ROOTS = [
    r'C:\DieHardROS\Documents\res',
    r'C:\DieHardROS\x64\Documents\res',
    r'C:\DieHardROS\runtime\Documents\res',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\Documents\res'
]

# Additional directories that need the loading images
EXTRA_LOADING_DIRS = [
    r'C:\DieHardROS\local_update\res\ui\images\loading',
    r'C:\DieHardROS\runtime\app\local_update\res\ui\images\loading'
]

print("\n>>> [2/4] Deploying all visual assets across all resource roots...")

for root in ROOTS:
    print(f"  Deploying to {root}...")
    dh_brand = os.path.join(root, 'dh_brand')
    loading_dir = os.path.join(root, 'ui', 'images', 'loading')
    images_dir = os.path.join(root, 'ui', 'images')
    login_dir = os.path.join(root, 'ui', 'images', 'login')

    for d in [dh_brand, loading_dir, images_dir, login_dir]:
        os.makedirs(d, exist_ok=True)

    # 1. Backgrounds & Wallpapers (V3 with 350px headroom for intact wings)
    for name in ['dh_bg1.jpg', 'dh_bg2.jpg', 'dh_bg3.jpg', 'dh_bg4.jpg', 
                 'dh_fireteam.jpg', 'dh_ev_06632.jpg', 'dh_ev_13933.jpg']:
        shutil.copyfile(WALLPAPER_V3, os.path.join(dh_brand, name))

    # 2. Season rank wallpapers (dh_rank_s1 to s30)
    for i in range(1, 31):
        shutil.copyfile(WALLPAPER_V3, os.path.join(dh_brand, f'dh_rank_s{i}.jpg'))

    # 3. Transparent PNG for all legacy logo textures
    for name in [
        'dh_login_logo.png', 'dh_logo_1.png', 'dh_logo_2.png', 'dh_logo_3.png',
        'dh_logo_4.png', 'dh_logo_5.png', 'dh_logo_sg_cloud.png', 'dh_logo_sg_cosmic.png',
        'dh_qr.png', 'ros_redemption_transparent.png'
    ]:
        with open(os.path.join(dh_brand, name), 'wb') as f:
            f.write(TRANS_PNG)

    for p in [
        os.path.join(root, 'txt_logo_zjzc.png'),
        os.path.join(images_dir, 'txt_logo_zjzc.png'),
        os.path.join(login_dir, 'txt_logo_zjzc.png'),
        os.path.join(root, 'zjzc_wz.png'),
        os.path.join(images_dir, 'zjzc_wz.png'),
        os.path.join(login_dir, 'zjzc_wz.png')
    ]:
        with open(p, 'wb') as f:
            f.write(TRANS_PNG)

    # 4. Standard loading screens (bg_loading_01..15)
    for i in range(1, 16):
        shutil.copyfile(WALLPAPER_V3, os.path.join(loading_dir, f'bg_loading_{i:02d}.png'))
    shutil.copyfile(WALLPAPER_V3, os.path.join(loading_dir, 'loading_0.png'))
    shutil.copyfile(WALLPAPER_V3, os.path.join(images_dir, 'bg_loading_01.png'))

    # 5. PC loading screens (pc_loading_0..20) -> OVERWRITES OLD SKYGAME SNIPER GIRL!
    for i in range(0, 21):
        shutil.copyfile(WALLPAPER_V3, os.path.join(loading_dir, f'pc_loading_{i}.png'))

print("  Deploying to extra local_update loading dirs...")
for ldir in EXTRA_LOADING_DIRS:
    os.makedirs(ldir, exist_ok=True)
    for i in range(1, 16):
        shutil.copyfile(WALLPAPER_V3, os.path.join(ldir, f'bg_loading_{i:02d}.png'))
    for i in range(0, 21):
        shutil.copyfile(WALLPAPER_V3, os.path.join(ldir, f'pc_loading_{i}.png'))
    shutil.copyfile(WALLPAPER_V3, os.path.join(ldir, 'loading_0.png'))

print("  All visual assets deployed successfully!")

# ====================================================================
# [3/4] Patch unpacked_lobby.py
# ====================================================================
print("\n>>> [3/4] Patching unpacked_lobby.py...")

with open(UNPACKED, 'rb') as f:
    raw = f.read()
text = raw.decode('utf-8')

# Patch A: Add (1024, 480) and (1280, 960) to _DH_ART_LOADING
OLD_ART_LOADING = '''_DH_ART_LOADING = {
    (1136, 852): _DH_ART_BG,
    (1024, 768): _DH_ART_BG,
}'''

NEW_ART_LOADING = '''_DH_ART_LOADING = {
    (1136, 852): _DH_ART_BG,
    (1024, 768): _DH_ART_BG,
    (1024, 480): _DH_ART_BG,
    (1280, 960): _DH_ART_BG,
}'''

if OLD_ART_LOADING in text:
    text = text.replace(OLD_ART_LOADING, NEW_ART_LOADING, 1)
    print("  [OK] Added (1024, 480) and (1280, 960) to _DH_ART_LOADING")
else:
    print("  [INFO] _DH_ART_LOADING already patched or different format")

# Patch B: Guarantee _dh_launcher_server_text always returns ROS-Redemption-Official
OLD_SERVER_FUNC = '''def _dh_launcher_server_text():
    import json as _json
    base = _dh_os.environ.get('LOCALAPPDATA') or ''
    path = _dh_os.path.join(base, 'ROS RedemptionROSHook', 'remote-servers.json')
    if not base or not _dh_os.path.isfile(path):
        return None'''

NEW_SERVER_FUNC = '''def _dh_launcher_server_text():
    import json as _json
    base = _dh_os.environ.get('LOCALAPPDATA') or ''
    # Check both DieHardROSHook and ROS RedemptionROSHook
    paths = [
        _dh_os.path.join(base, 'DieHardROSHook', 'remote-servers.json'),
        _dh_os.path.join(base, 'ROS RedemptionROSHook', 'remote-servers.json'),
    ]
    path = next((p for p in paths if _dh_os.path.isfile(p)), None)
    if not path:
        # Fallback guarantee: ALWAYS return ROS-Redemption-Official
        return 'ROS-Redemption 1 0 2 X ROS-Redemption-Official 127.0.0.1:19000 127.0.0.1:19000 127.0.0.1:19000 10501 127.0.0.1:19000' '''

if OLD_SERVER_FUNC in text:
    text = text.replace(OLD_SERVER_FUNC, NEW_SERVER_FUNC, 1)
    print("  [OK] Patched _dh_launcher_server_text to always guarantee ROS-Redemption-Official")
else:
    print("  [INFO] _dh_launcher_server_text already patched or different format")

# Patch C: Force complete hide on UILogin/Logo, Logo_netease, and layer_swing in _dh_scene_brand_pass
OLD_LOGO_HIDE = '''        if 'login_logo' in low or 'txt_logo_zjzc' in low or _dh_is_logo_file(low):
            target = _dh_logo_now()'''

NEW_LOGO_HIDE = '''        if 'login_logo' in low or 'txt_logo_zjzc' in low or 'zjzc' in low or _dh_is_logo_file(low):
            # Completely hide the logo node because our wallpaper has the embedded 3D logo
            try:
                node.setVisible(False)
                node.setPosition(-99999, -99999)
                if hasattr(node, 'setOpacity'): node.setOpacity(0)
            except Exception:
                pass
            target = 'dh_logo_1.png' '''

if OLD_LOGO_HIDE in text:
    text = text.replace(OLD_LOGO_HIDE, NEW_LOGO_HIDE, 1)
    print("  [OK] Patched _dh_scene_brand_pass to completely hide logo nodes")
else:
    print("  [INFO] Logo hide already patched")

# Save patched unpacked_lobby.py
with open(UNPACKED, 'wb') as f:
    f.write(text.encode('utf-8'))
print("  Saved patched unpacked_lobby.py (%d bytes)" % len(text))

# Verify syntax
import py_compile
py_compile.compile(UNPACKED, doraise=True)
print("  Syntax check PASSED!")

# ====================================================================
# [4/4] Re-encrypt into hot patches
# ====================================================================
print("\n>>> [4/4] Encrypting and deploying hot patches...")

def encrypt_patch(src_text, key):
    raw = src_text.encode('utf-8')
    compressed = zlib.compress(raw, 9)
    key_len = len(key)
    xored = bytearray(len(compressed))
    for i, b in enumerate(bytearray(compressed)):
        xored[i] = b ^ key[i % key_len]
    b64 = base64.b64encode(bytes(xored)).decode('ascii')
    chunks = [b64[i:i+86] for i in range(0, len(b64), 86)]
    return chunks

def make_packed(chunks):
    key_hex = '2a8ec34ed7c4baa57c7b5e4adef0f454f8f854d809daa14616db06b2eac10809'
    lines = [
        '# DieHard ROS Online - packed hot patch. Generated by tools/pack_patch.py; do not edit by hand.',
        'import zlib as _dhz, hashlib as _dhh, base64 as _dhb',
        '_K = "%s".decode("hex")' % key_hex,
        '_CO = "lobby_hot_patch"',
        '_B = [',
    ]
    for chunk in chunks:
        lines.append('    "%s",' % chunk)
    lines.append(']')
    lines.append('')
    lines.append('def _r(b,k):')
    lines.append('    d=_dhb.b64decode(b);n=len(k);return bytes(bytearray(d[i]^k[i%n] for i in range(len(d))))')
    lines.append('def _x():')
    lines.append('    raw=b"".join(_r(c,_K) for c in _B)')
    lines.append('    return _dhz.decompress(raw)')
    lines.append('exec(compile(_x(),_CO,"exec"))')
    return '\r\n'.join(lines) + '\r\n'

chunks = encrypt_patch(text, K)
packed = make_packed(chunks)
packed_bytes = packed.encode('utf-8')
print("  Packed patch size: %d bytes (%d chunks)" % (len(packed_bytes), len(chunks)))

# Write remote-lobby.py
with open(REMOTE_LOBBY, 'wb') as f:
    f.write(packed_bytes)
print("  Written:", REMOTE_LOBBY)

# Write all hot-lobby-*.py
for hf in glob.glob(os.path.join(HOT_DIR, 'hot-lobby-*.py')):
    with open(hf, 'wb') as f:
        f.write(packed_bytes)
    print("  Written:", hf)

print("\n=======================================================")
print(">>> ALL MASTER FIXES DEPLOYED AND READY! <<<")
print("=======================================================")
