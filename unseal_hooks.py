import os
import sys
from pathlib import Path

# Add runtime app to sys.path so we can import client.sealed
sys.path.insert(0, r"C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app")
import rrboot
rrboot.install()

from client import sealed

battle_hook_path = Path(r"c:\Users\seanj\dev\server_extracted\client\battle_hook.py")
lobby_hook_path = Path(r"c:\Users\seanj\dev\server_extracted\client\lobby_hook.py")

battle_src = sealed.read_source(battle_hook_path)
with open(r"c:\Users\seanj\dev\battle_hook_unsealed.py", "w", encoding="utf-8") as f:
    f.write(battle_src)
print("Unsealed battle_hook.py! Length:", len(battle_src))

lobby_src = sealed.read_source(lobby_hook_path)
with open(r"c:\Users\seanj\dev\lobby_hook_unsealed.py", "w", encoding="utf-8") as f:
    f.write(lobby_src)
print("Unsealed lobby_hook.py! Length:", len(lobby_src))

