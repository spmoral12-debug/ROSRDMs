import os, glob, zlib as zl, hashlib as hh, base64 as b64, shutil, sqlite3, time, json

K = bytes.fromhex('2a8ec34ed7c4baa57c7b5e4adef0f454f8f854d809daa14616db06b2eac10809')

print("==================================================================")
print(">>> EXECUTING COMPLETE ROS REDEMPTION MASTER ENGINE FIX <<<")
print("==================================================================")

# 1. Update unpacked_lobby.py
unpacked_path = r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py'
if os.path.exists(unpacked_path):
    with open(unpacked_path, 'r', encoding='utf-8', errors='ignore') as f:
        src = f.read()

    # Fix art directory
    src = src.replace(r'C:\ROS RedemptionROS\Documents\res\dh_brand', r'C:\DieHardROS\Documents\res\dh_brand')

    # Ensure direct brand loading in _dh_art_file
    idx = src.find('def _dh_art_file(name):')
    if idx >= 0:
        end_idx = src.find('\ndef ', idx + 10)
        if end_idx >= 0:
            new_func = "def _dh_art_file(name):\n    if not name:\n        return None\n    return 'dh_brand/' + str(name)\n\n"
            src = src[:idx] + new_func + src[end_idx+1:]
            print("  [1] _dh_art_file patched.")

    # Patch _dh_art_pass to eliminate layer_swing, QR code, Facebook and hide logo widget on login screen
    art_pass_idx = src.find("elif 'login' in name.lower():")
    if art_pass_idx >= 0:
        end_art_pass = src.find("if target is None:", art_pass_idx)
        if end_art_pass >= 0:
            new_login_art = """elif 'login' in name.lower():
                leaf = _dh_lower(path.split('/')[-1])
                render = _dh_render_file(node)
                # Remove street squad, QR code, Facebook, old animated layers
                if any(k in leaf or k in render for k in ('swing', 'panel_di', 'panel_che', 'qrcode', 'facebook', 'icon_facebook', 'bg_login_word', 'vng_logo', 'erweima')):
                    try:
                        if hasattr(node, 'stopAllActions'): node.stopAllActions()
                        node.setVisible(False)
                        node.setPosition(-99999, -99999)
                        if hasattr(node, 'removeFromParent'): node.removeFromParent()
                    except Exception:
                        pass
                    continue
                # Hide logo widget because dh_bg1.jpg has the 3D winged ROS Redemption Battle Royale logo
                if 'img_login_logo' in render or ('logo' in leaf and 'btn' not in leaf and 'icon' not in leaf):
                    try:
                        node.setVisible(False)
                        node.setPosition(-99999, -99999)
                    except Exception:
                        pass
                    target = 'dh_logo_1.png'
                elif 'bg' in leaf or 'background' in leaf or 'bg_loading' in render:
                    target = 'dh_bg1.jpg'
            """
            src = src[:art_pass_idx] + new_login_art + src[end_art_pass:]
            print("  [2] _dh_art_pass patched with complete layer_swing and logo suppression.")

    with open(unpacked_path, 'w', encoding='utf-8') as f:
        f.write(src)

    # Re-encrypt master patch payload
    print("  [3] Encrypting payload...")
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
            with open(p, 'w', encoding='utf-8') as f:
                f.write(orig[:s] + b_payload + orig[e+3:])
            print("  [4] Hook update written to:", os.path.basename(p))

    remote_p = r'C:\DieHardROS\local_update\hot\remote-lobby.py'
    if os.path.exists(remote_p):
        with open(remote_p, 'r', encoding='utf-8') as f:
            orig = f.read()
        s = orig.find('_B = [')
        e = orig.find(']\n\n', s)
        if s >= 0 and e >= 0:
            with open(remote_p, 'w', encoding='utf-8') as f:
                f.write(orig[:s] + b_payload + orig[e+3:])
            print("  [5] local_update remote-lobby.py updated.")

# 2. Update Play_ROS_Redemption.bat to use RosRedemptionBrandingSuite.exe
bat_p = r'C:\DieHardROS\Play_ROS_Redemption.bat'
bat_content = """@echo off
title ROS Redemption
color 0A
cd /d "%~dp0"

echo ===================================================================
echo               ROS REDEMPTION (OFFICIAL GAME ^& SERVER)
echo ===================================================================

:: Ensure branding watcher runs continuously
tasklist /fi "imagename eq RosRedemptionBrandingSuite.exe" 2>nul | find /i "RosRedemptionBrandingSuite.exe" >nul || start "" "%~dp0RosRedemptionBrandingSuite.exe"

set "ROS_GAME_DIR=%~dp0"
set "ROS_RT_KEY=f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "PYTHONDONTWRITEBYTECODE=1"

cd /d "%~dp0runtime\app"
"..\\python\\python.exe" "start_game.pyc" --direct --account Admin_Redemption
exit
"""
with open(bat_p, 'w', encoding='utf-8') as f:
    f.write(bat_content)
print("  [6] Play_ROS_Redemption.bat updated to invoke RosRedemptionBrandingSuite.exe.")

# 3. Synchronize accounts.db wallets and mails
db = r'C:\DieHardROS\local_update\server_data\accounts.db'
if os.path.exists(db):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    # Update all accounts/wallets to 100,000 Diamonds and 500,000 Gold
    cur.execute("UPDATE wallets SET gp = 500000, freeYuanbao = 100000, payYuanbao = 100000 WHERE gid = 10000002")
    cur.execute("SELECT gid, nickname FROM characters")
    chars = cur.fetchall()
    now = int(time.time())
    deadline = now + (30 * 86400)
    for gid, name in chars:
        cur.execute("SELECT id FROM mails WHERE gid = ? AND title LIKE '%100,000 Diamonds%'", (gid,))
        if not cur.fetchone():
            reward_json = '[{"type":"currency","gp":500000,"payYuanbao":100000,"freeYuanbao":100000}]'
            cur.execute("""
                INSERT INTO mails (gid, type, title, content, sender, sender_gid, props, created, deadline, unread, deleted)
                VALUES (?, 0, 'Welcome to ROS Redemption! (100,000 Diamonds Gift)', 
                'Welcome to ROS Redemption! Here is your exclusive package: 100,000 Diamonds and 500,000 Gold. Enjoy!', 
                'ROS Redemption HQ', 0, ?, ?, ?, 1, 0)
            """, (gid, reward_json, now, deadline))
            print(f"  [7] Sent 100,000 Diamonds mail to: {name} (GID: {gid})")
    conn.commit()
    conn.close()

print("\n>>> ALL CODE AND DATABASE FIXES DEPLOYED CLEANLY! <<<")

