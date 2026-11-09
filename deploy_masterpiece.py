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

art_engine = """

# ==========================================================================
# ROS REDEMPTION: MASTERPIECE LOGIN WALLPAPER INJECTOR
# ==========================================================================
_dh_screens_state = {'open': {}}

def _dh_swap_tex(node, rel):
    try:
        import cc
        tex = cc.Director.getInstance().getTextureCache().addImage(rel)
        if hasattr(node, 'loadTexture'):
            node.loadTexture(rel)
        elif hasattr(node, 'setTexture') and tex:
            node.setTexture(tex)
    except:
        pass

def _dh_run_art_swap(name, ui):
    try:
        import cc
        
        # 1. Ilapat ang 16:9 ROS REDEMPTION Masterpiece Wallpaper sa mismong PLAY Screen
        if 'login' in name.lower() and not getattr(ui, '_has_masterpiece_bg', False):
            try:
                win = cc.Director.getInstance().getWinSize()
                bg = cc.Sprite.create('dh_brand/dh_bg1.jpg')
                if bg:
                    bg.setPosition(win.width / 2.0, win.height / 2.0)
                    sz = bg.getContentSize()
                    if sz.width > 0 and sz.height > 0:
                        bg.setScaleX(float(win.width) / float(sz.width))
                        bg.setScaleY(float(win.height) / float(sz.height))
                    # Ipatong sa z-order -1: Sa likod ng buttons, pero tatakpan ang lumang squad!
                    ui.addChild(bg, -1)
                    ui._has_masterpiece_bg = True
            except:
                pass

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
                        except:
                            pass
                
                # 2. Loading Screen background swap
                if 'loading' in name.lower() and ('bg' in leaf or 'background' in leaf or 'pic' in leaf):
                    _dh_swap_tex(node, 'dh_brand/dh_bg1.jpg')

                # 3. Sa Login Screen: Itago ang hiwalay na logo box (dahil nakapinta na sa wallpaper ang logo!)
                if 'login' in name.lower():
                    if 'img_login_logo' in render or ('logo' in leaf and 'btn' not in leaf):
                        try:
                            node.setVisible(False)
                        except:
                            pass
                    # Palitan ang anumang 2D background widget
                    if 'bg' in leaf or 'background' in leaf:
                        _dh_swap_tex(node, 'dh_brand/dh_bg1.jpg')

                # 4. Tanggalin ang SkyGame website ribbon
                txt = _node_text(node)
                setter = _node_setter(node)
                if txt:
                    t_low = txt.lower()
                    if 'skygame' in t_low or 'official website' in t_low:
                        try:
                            node.setVisible(False)
                            p = node.getParent()
                            if p: p.setVisible(False)
                        except:
                            pass
                        if setter: setter('')
                    if 'elect server' in t_low or 'select server' in t_low:
                        if setter: setter('Fast ROS-Redemption-Official')
            except:
                pass
    except:
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
    except:
        pass
    call_later(0.5, _dh_check_screens)

try:
    call_later(0.5, _dh_check_screens)
except:
    pass
"""

src += art_engine

with open(hook_file, "w", encoding="utf-8") as f:
    f.write(src)

print(">>> Masterpiece Wallpaper Hook deployed successfully!")
