import sys, os

sys.path.insert(0, r"C:\DieHardROS\runtime\app")
os.environ['ROS_RT_KEY'] = 'f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf'

import rrboot
rrboot.install()
import client.inject_lobby as inj

hook_file = r"C:\DieHardROS\runtime\app\client\lobby_hook.py"
if os.path.exists(hook_file):
    os.remove(hook_file)

src = inj.read_source(inj.HOOK_PATH)

# String rewrites
replacements = [
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
]
for old, rep in replacements:
    src = src.replace(old, rep)

art_engine = """

# ==========================================================================
# ROS REDEMPTION: COMPLETE LOGIN BG & LOGO REPLACER
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

def _dh_swap_logo_fit(node, file_rel):
    try:
        import cc
        tex = cc.Director.getInstance().getTextureCache().addImage(file_rel)
        if hasattr(node, 'loadTexture'):
            node.loadTexture(file_rel)
        elif hasattr(node, 'setTexture') and tex is not None:
            node.setTexture(tex)
        try:
            win = cc.Director.getInstance().getWinSize()
            size = node.getContentSize()
            w1, h1 = float(size.width), float(size.height)
            if w1 > 0 and h1 > 0:
                fit = min(0.40 * float(win.width) / w1, 0.32 * float(win.height) / h1)
                node.setScaleX(fit)
                node.setScaleY(fit)
        except Exception:
            pass
    except Exception:
        pass

def _dh_run_art_swap(name, ui):
    try:
        import cc
        
        # 1. Piliting maglagay ng full-screen ROS Redemption background sa UILogin
        if 'login' in name.lower() and not getattr(ui, '_has_redemption_bg', False):
            try:
                win = cc.Director.getInstance().getWinSize()
                bg_sprite = cc.Sprite.create('dh_brand/dh_bg1.jpg')
                if bg_sprite:
                    bg_sprite.setPosition(win.width / 2.0, win.height / 2.0)
                    sz = bg_sprite.getContentSize()
                    if sz.width > 0 and sz.height > 0:
                        bg_sprite.setScaleX(float(win.width) / float(sz.width))
                        bg_sprite.setScaleY(float(win.height) / float(sz.height))
                    ui.addChild(bg_sprite, -100)
                    ui._has_redemption_bg = True
            except Exception:
                pass
        
        for path, node in walk_ui_nodes(ui, limit=1200):
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
                
                # 2. Loading screen background
                if 'loading' in name.lower():
                    if 'bg' in leaf or 'background' in leaf or 'pic' in leaf:
                        _dh_swap_texture(node, 'dh_brand/dh_bg1.jpg')
                
                # 3. Login screen background widget
                if 'login' in name.lower():
                    if 'bg' in leaf or 'background' in leaf:
                        _dh_swap_texture(node, 'dh_brand/dh_bg1.jpg')
                    
                    # 4. PALITAN ANG ROS LEGACY SA GITNA NG ROS REDEMPTION TRANSPARENT LOGO!
                    if 'img_login_logo' in render or ('logo' in leaf and 'btn' not in leaf):
                        _dh_swap_logo_fit(node, 'dh_brand/ros_redemption_transparent.png')
                
                # 5. Tanggalin nang buo ang SkyGame website banner at icon ng bahay
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
                    
                    if 'elect server' in t_low or 'select server' in t_low:
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
                for delay in (0.0, 0.1, 0.3, 0.6, 1.2, 2.0, 3.5):
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

src += art_engine

with open(hook_file, "w", encoding="utf-8") as f:
    f.write(src)

print(">>> Clean ROS Redemption Hook with Full BG & Logo Replacement Ready!")
