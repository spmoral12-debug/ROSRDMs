import sys, os
from pathlib import Path

sys.path.insert(0, r"C:\DieHardROS\runtime\app")
os.environ['ROS_RT_KEY'] = 'f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf'

import rrboot
rrboot.install()

import client.inject_lobby as inj

# Burahin muna ang corrupted file para mabasa ang original sealed base
hook_disk = r"C:\DieHardROS\runtime\app\client\lobby_hook.py"
if os.path.exists(hook_disk):
    os.remove(hook_disk)

# Basahin ang totoong base hook mula sa code.rrx
src = inj.read_source(inj.HOOK_PATH)
print(f">>> Original base hook extracted! ({len(src)} characters)")

# Rebrand sa ROS Redemption
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

# I-save bilang plain python file para ito na ang direktang patakbuhin ng laro
os.makedirs(os.path.dirname(hook_disk), exist_ok=True)
with open(hook_disk, 'w', encoding='utf-8') as f:
    f.write(src)
print(">>> Successfully saved clean base hook to:", hook_disk)
