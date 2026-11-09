import sys, os

sys.path.insert(0, r"C:\DieHardROS\runtime\app")
os.environ['ROS_RT_KEY'] = 'f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf'

import rrboot
rrboot.install()
import client.inject_lobby as inj

# Kunin ang authentic unsealed base hook
hook_file = r"C:\DieHardROS\runtime\app\client\lobby_hook.py"
if os.path.exists(hook_file):
    os.remove(hook_file)

src = inj.read_source(inj.HOOK_PATH)

# Palitan ang lahat ng lumang branding text
for old, rep in [
    ('ros.skygame.io', 'ROS REDEMPTION'),
    ('DieHard ROS Online', 'ROS Redemption'),
    ('DieHard ROS', 'ROS Redemption'),
    ('DieHard', 'ROS Redemption'),
    ('roslegacy.net', 'ROS REDEMPTION'),
    ('ROS LEGACY', 'ROS REDEMPTION'),
    ('ros legacy', 'ROS Redemption')
]:
    src = src.replace(old, rep)

# Idagdag ang Dynamic Screen & Art Swapper sa dulo ng hook
art_block = """

# ==========================================================================
# ROS REDEMPTION: AUTOMATIC SCREEN & LOGO SWAPPER HOOK
# ==========================================================================
_dh_screens_state = {'open': {}}

def _dh_cc_inst():
    try:
        import cc
        return cc
    except Exception:
        return None

def _dh_swap_texture(node, file_rel):
    try:
        cc = _dh_cc_inst()
        if cc is None: return False
        tex = cc.Director.getInstance().getTextureCache().addImage(file_rel)
        if hasattr(node, 'loadTexture'):
            node.loadTexture(file_rel)
        elif hasattr(node, 'setTexture') and tex is not None:
            node.setTexture(tex)
        else:
            return False
        return True
    except Exception:
        return False

def _dh_swap_logo_fit(node, file_rel):
    try:
        cc = _dh_cc_inst()
        if cc is None: return False
        tex = cc.Director.getInstance().getTextureCache().addImage(file_rel)
        if hasattr(node, 'loadTexture'):
            node.loadTexture(file_rel)
        elif hasattr(node, 'setTexture') and tex is not None:
            node.setTexture(tex)
        else:
            return False
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
                
                target = None
                is_logo = False
                if 'loading' in name.lower():
                    if 'bg' in leaf or 'background' in leaf or 'loading' in leaf or 'pic' in leaf or 'img' in leaf:
                        target = 'dh_brand/dh_bg1.jpg'
                elif 'login' in name.lower():
                    if 'bg' in leaf or 'background' in leaf:
                        target = 'dh_brand/dh_bg1.jpg'
                    elif 'img_login_logo' in render or ('logo' in leaf and 'btn' not in leaf):
                        target = 'dh_brand/dh_logo_1.png'
                        is_logo = True
                
                if target:
                    if is_logo:
                        _dh_swap_logo_fit(node, target)
                    else:
                        _dh_swap_texture(node, target)
            except Exception:
                pass
    except Exception:
        pass

def _dh_check_screens():
    try:
        import Globals
        for name in ('UILogin', 'UILoading', 'UISelectCharacter'):
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

print(">>> Lobby Hook successfully patched with ROS Redemption Art Engine!")
