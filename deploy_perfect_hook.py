import sys, os

sys.path.insert(0, r"C:\DieHardROS\runtime\app")
os.environ['ROS_RT_KEY'] = 'f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf'

import rrboot
rrboot.install()
import client.inject_lobby as inj

hook_file = r"C:\DieHardROS\runtime\app\client\lobby_hook.py"
if os.path.exists(hook_file):
    os.remove(hook_file)

# Kunin ang malinis na original base
src = inj.read_source(inj.HOOK_PATH)

# Palitan ang lahat ng lumang branding text
for old, rep in [
    ('ros.skygame.io', ''),
    ('Official website:', ''),
    ('Official website', ''),
    ('DieHard ROS Online', 'ROS Redemption'),
    ('DieHard ROS', 'ROS Redemption'),
    ('DieHard', 'ROS Redemption'),
    ('roslegacy.net', ''),
    ('ROS LEGACY', 'ROS REDEMPTION'),
    ('ros legacy', 'ROS Redemption'),
    ('Select Server', 'ROS-Redemption-Official'),
    ('elect Server', '')
]:
    src = src.replace(old, rep)

# Idagdag ang automatic screen swapper sa dulo
art_block = """

# ==========================================================================
# ROS REDEMPTION: SCREEN SWAPPER & BANNER REMOVER
# ==========================================================================
_dh_screens_state = {'open': {}}

def _dh_swap_texture(node, file_rel):
    try:
        import cc
        tex = cc.Director.getInstance().getTextureCache().addImage(file_rel)
        if hasattr(node, 'loadTexture'):
            node.loadTexture(file_rel)
        elif hasattr(node, 'setTexture') and tex is not None:
            node.setTexture(tex)
    except Exception:
        pass

def _dh_run_art_swap(name, ui):
    try:
        for path, node in walk_ui_nodes(ui, limit=1000):
            try:
                leaf = path.split('/')[-1].lower()
                render = ''
                for getter in ('getRenderFile', 'getTextureFile', 'getBackGroundImageFile'):
                    fn = getattr(node, getter, None)
                    if callable(fn):
                        try:
                            render = str(fn()).lower()
                            break
                        except Exception:
                            pass
                
                # 1. Loading background swap
                if 'loading' in name.lower():
                    if 'bg' in leaf or 'background' in leaf or 'pic' in leaf:
                        _dh_swap_texture(node, 'dh_brand/dh_bg1.jpg')
                
                # 2. Tanggalin nang buo ang SkyGame website banner at icon
                text = _node_text(node)
                setter = _node_setter(node)
                if text:
                    t_low = text.lower()
                    if 'skygame' in t_low or 'official website' in t_low or 'website' in t_low:
                        try:
                            node.setVisible(False)
                            parent = node.getParent()
                            if parent: parent.setVisible(False)
                        except Exception:
                            pass
                        if setter: setter('')
                    
                    if 'elect server' in t_low:
                        if setter: setter('Fast ROS-Redemption-Official')
            except Exception:
                pass
    except Exception:
        pass

def _dh_check_screens():
    try:
        import Globals
        for name in ('UILogin', 'UILoading'):
            ui = getattr(Globals.uiMgr, name, None)
            was = _dh_screens_state['open'].get(name)
            now = id(ui) if ui is not None else None
            if now is not None and now != was:
                for delay in (0.0, 0.2, 0.5, 1.2, 2.5):
                    call_later(delay, _dh_run_art_swap, name, ui)
            _dh_screens_state['open'][name] = now
    except Exception:
        pass
    call_later(0.5, _dh_check_screens)

try:
    call_later(0.5, _dh_check_screens)
except Exception:
    pass
"""

src += art_block

with open(hook_file, "w", encoding="utf-8") as f:
    f.write(src)

print(">>> Clean ROS Redemption Hook successfully deployed!")
