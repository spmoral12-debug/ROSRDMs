import os, shutil

src_path = r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py'
with open(src_path, 'r', encoding='utf-8', errors='ignore') as f:
    src = f.read()

# 1. Palitan ang lahat ng natitirang DieHard, SkyGame, at ROS Legacy strings
for old, rep in [
    ('ros.skygame.io', 'ROS REDEMPTION'),
    ('DieHard ROS Online', 'ROS Redemption'),
    ('DieHard ROS', 'ROS Redemption'),
    ('DieHard', 'ROS Redemption'),
    ('roslegacy.net', 'ROS REDEMPTION'),
    ('ros legacy', 'ROS Redemption'),
    ('ROS LEGACY', 'ROS REDEMPTION')
]:
    src = src.replace(old, rep)

# 2. Siguraduhing diretsong ibinabalik ang C:\DieHardROS\Documents\res\dh_brand
idx = src.find('def _dh_art_dir():')
if idx >= 0:
    end_idx = src.find('\ndef ', idx + 10)
    if end_idx >= 0:
        src = src[:idx] + "def _dh_art_dir():\n    return r'C:\\DieHardROS\\Documents\\res\\dh_brand'\n\n" + src[end_idx+1:]

# 3. Siguraduhing laging ibinabalik ang relative filename
idx = src.find('def _dh_art_file(name):')
if idx >= 0:
    end_idx = src.find('\ndef ', idx + 10)
    if end_idx >= 0:
        src = src[:idx] + "def _dh_art_file(name):\n    if not name: return None\n    return 'dh_brand/' + str(name)\n\n" + src[end_idx+1:]

# 4. Ayusin ang Cocos CCTexture2D swap para sa CCSprite
new_swap = """def _dh_swap(key, node, file_path):
    try:
        cc = _dh_cc()
        if cc is None: return False
        tex = cc.Director.getInstance().getTextureCache().addImage(file_path)
        if hasattr(node, 'loadTexture'): node.loadTexture(file_path)
        elif hasattr(node, 'setTexture') and tex is not None: node.setTexture(tex)
        else: return False
        return True
    except Exception:
        return False

def _dh_swap_logo(key, node, file_path):
    try:
        cc = _dh_cc()
        if cc is None: return False
        tex = cc.Director.getInstance().getTextureCache().addImage(file_path)
        if hasattr(node, 'loadTexture'): node.loadTexture(file_path)
        elif hasattr(node, 'setTexture') and tex is not None: node.setTexture(tex)
        else: return False
        try:
            win = cc.Director.getInstance().getWinSize()
            size = node.getContentSize()
            w1, h1 = float(size.width), float(size.height)
            if w1 > 0 and h1 > 0:
                fit = min(0.35 * float(win.width) / w1, 0.28 * float(win.height) / h1)
                node.setScaleX(fit)
                node.setScaleY(fit)
        except Exception:
            pass
        return True
    except Exception:
        return False
"""

idx = src.find('def _dh_swap(key, node, file_path):')
if idx >= 0:
    end_idx = src.find('def _dh_typed_widget(ui, path):', idx)
    if end_idx >= 0:
        src = src[:idx] + new_swap + "\n\n" + src[end_idx:]

# Banner sa pinakataas
banner = "print('\\n' + '='*65 + '\\n>>> [ROS REDEMPTION] MASTER HOOK 100% ACTIVE! <<<\\n' + '='*65 + '\\n')\n"
src = banner + src

# I-save sa runtime\app\client\lobby_hook.py
targets = [
    r'C:\DieHardROS\runtime\app\client\lobby_hook.py',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app\client\lobby_hook.py'
]

for t in targets:
    os.makedirs(os.path.dirname(t), exist_ok=True)
    with open(t, 'w', encoding='utf-8') as f:
        f.write(src)
    print(">>> Written hook to:", t)

print(">>> DIRECT LOBBY HOOK DEPLOYED SUCCESSFULLY!")
