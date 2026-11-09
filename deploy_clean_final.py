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

art_code = """

# ==========================================================================
# ROS REDEMPTION ENGINE INJECTOR
# ==========================================================================
_dh_screens_state = {'open': {}}

def _dh_swap_login_bg(ui):
    try:
        import cc
        win = cc.Director.getInstance().getWinSize()
        tex = cc.Director.getInstance().getTextureCache().addImage('dh_brand/dh_bg1.jpg')
        if tex is not None and not getattr(ui, '_dh_custom_bg_sprite', False):
            sp = cc.Sprite.createWithTexture(tex)
            if sp is not None:
                sp.setPosition(win.width / 2.0, win.height / 2.0)
                sz = sp.getContentSize()
                if sz.width > 0 and sz.height > 0:
                    sp.setScaleX(float(win.width) / float(sz.width))
                    sp.setScaleY(float(win.height) / float(sz.height))
                ui.addChild(sp, -1)
                ui._dh_custom_bg_sprite = True
    except Exception:
        pass

def _dh_swap_logo(node):
    try:
        import cc
        tex = cc.Director.getInstance().getTextureCache().addImage('dh_brand/dh_logo_1.png')
        if tex is not None:
            if hasattr(node, 'setTexture'):
                node.setTexture(tex)
            win = cc.Director.getInstance().getWinSize()
            sz = node.getContentSize()
            if sz.width > 0 and sz.height > 0:
                fit = min(0.42 * float(win.width) / float(sz.width), 0.32 * float(win.height) / float(sz.height))
                node.setScaleX(fit)
                node.setScaleY(fit)
    except Exception:
        pass

def _dh_run_art_swap(name, ui):
    try:
        if 'login' in name.lower():
            _dh_swap_login_bg(ui)
            
        for path, node in walk_ui_nodes(ui, limit=1200):
            try:
                leaf = path.split('/')[-1].lower()
                render = ''
                for g in ('getRenderFile', 'getTextureFile', 'getBackGroundImageFile'):
                    fn = getattr(node, g, None)
                    if callable(fn):
                        try:
                            render = str(fn()).lower()
                            break
                        except Exception:
                            pass
                
                # Palitan ang Logo sa gitna gamit ang Transparent ROS Redemption
                if 'login' in name.lower():
                    if 'img_login_logo' in render or ('logo' in leaf and 'btn' not in leaf):
                        _dh_swap_logo(node)

                # Tanggalin ang SkyGame ribbon
                txt = _node_text(node)
                setter = _node_setter(node)
                if txt:
                    t_low = txt.lower()
                    if 'skygame' in t_low or 'official website' in t_low:
                        try:
                            node.setVisible(False)
                            p = node.getParent()
                            if p: p.setVisible(False)
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
            now = id(ui) if ui else None
            if now and now != was:
                for d in (0.0, 0.1, 0.2, 0.5, 1.0, 2.0, 3.5):
                    call_later(d, _dh_run_art_swap, name, ui)
            _dh_screens_state['open'][name] = now
    except Exception:
        pass
    call_later(0.5, _dh_check_screens)

try:
    call_later(0.5, _dh_check_screens)
except Exception:
    pass
"""

src += art_code

with open(hook_file, "w", encoding="utf-8") as f:
    f.write(src)

print(">>> Clean Hook successfully deployed!")
