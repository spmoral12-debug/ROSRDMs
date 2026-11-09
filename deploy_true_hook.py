import sys, os
from pathlib import Path

sys.path.insert(0, r"C:\DieHardROS\runtime\app")
os.environ['ROS_RT_KEY'] = 'f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf'

import rrboot
rrboot.install()

import client.inject_lobby as inj

# Tanggalin muna ang may error na file para basahin ang sealed original
hook_disk = r"C:\DieHardROS\runtime\app\client\lobby_hook.py"
if os.path.exists(hook_disk):
    os.remove(hook_disk)

appdata_hook = r"C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app\client\lobby_hook.py"
if os.path.exists(appdata_hook):
    os.remove(appdata_hook)

# Basahin ang totoong original working base hook mula sa code.rrx
src = inj.read_source(inj.HOOK_PATH)
print(f">>> Original base hook loaded successfully! ({len(src)} characters)")

# Rebrand lahat ng DieHard, SkyGame, at ROS Legacy
for old, rep in [
    ('ros.skygame.io', 'ROS REDEMPTION'),
    ('DieHard ROS Online', 'ROS Redemption'),
    ('DieHard ROS', 'ROS Redemption'),
    ('DieHard', 'ROS Redemption'),
    ('roslegacy.net', 'ROS REDEMPTION'),
    ('ros legacy', 'ROS Redemption'),
    ('ROS LEGACY', 'ROS REDEMPTION'),
    ('SkyGame', 'ROS Redemption')
]:
    src = src.replace(old, rep)

# Siguraduhing sa C:\DieHardROS\Documents\res\dh_brand kukunin ang visual assets
idx = src.find('def _dh_art_dir():')
if idx >= 0:
    end_idx = src.find('\ndef ', idx + 10)
    if end_idx >= 0:
        src = src[:idx] + "def _dh_art_dir():\n    return r'C:\\DieHardROS\\Documents\\res\\dh_brand'\n\n" + src[end_idx+1:]

# I-save ang na-rebrand na totoong base hook
with open(hook_disk, 'w', encoding='utf-8') as f:
    f.write(src)
print(">>> Saved clean ROS Redemption base hook to:", hook_disk)

os.makedirs(os.path.dirname(appdata_hook), exist_ok=True)
with open(appdata_hook, 'w', encoding='utf-8') as f:
    f.write(src)

print(">>> BASE HOOK DEPLOYMENT 100% COMPLETE!")
