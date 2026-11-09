import os, sys, shutil

helmet = r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_pure_emblem_1794029947671.jpg"
splash = r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_splash_clean_1794018381576.jpg"
logo   = r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_title_logo_1794018691342.jpg"

# 1. Palitan ang splash.png at icon.png sa runtime\app (Eto yung lumulutang na asul na controller!)
for target in [
    r"C:\DieHardROS\runtime\app\splash.png",
    r"C:\DieHardROS\runtime\app\icon.png",
    r"C:\DieHardROS\Documents\res\dh_brand\dh_logo_sg_cloud.png",
    r"C:\DieHardROS\Documents\res\dh_brand\dh_logo_sg_cosmic.png"
]:
    try:
        shutil.copyfile(helmet, target)
        print("Replaced splash/icon:", target)
    except Exception as e:
        print("Error:", e)

# 2. Palitan ang lahat ng backgrounds sa dh_brand gamit ang ROS Redemption Splash Art
for bg in ['dh_bg1.jpg', 'dh_bg2.jpg', 'dh_bg3.jpg', 'dh_bg4.jpg', 'dh_fireteam.jpg', 'dh_ev_06632.jpg', 'dh_ev_13933.jpg']:
    p = os.path.join(r"C:\DieHardROS\Documents\res\dh_brand", bg)
    try:
        shutil.copyfile(splash, p)
    except:
        pass

# 3. Palitan ang logos sa dh_brand
for l in ['dh_logo_1.png', 'dh_logo_2.png', 'dh_logo_3.png', 'dh_logo_4.png', 'dh_logo_5.png', 'dh_login_logo.png']:
    p = os.path.join(r"C:\DieHardROS\Documents\res\dh_brand", l)
    try:
        shutil.copyfile(logo, p)
    except:
        pass

# 4. Ayusin ang Lobby Hook
base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(base_dir, "runtime", "app"))
os.environ['ROS_RT_KEY'] = 'f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf'
import rrboot
rrboot.install()
import client.inject_lobby as inj

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

# ROS REDEMPTION AUTO-SWAP ENGINE
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

def _dh_swap_logo(node, rel):
    try:
        import cc
        tex = cc.Director.getInstance().getTextureCache().addImage(rel)
        if hasattr(node, 'loadTexture'):
            node.loadTexture(rel)
        elif hasattr(node, 'setTexture') and tex:
            node.setTexture(tex)
        try:
            win = cc.Director.getInstance().getWinSize()
            sz = node.getContentSize()
            if sz.width > 0 and sz.height > 0:
                fit = min(0.40 * float(win.width) / float(sz.width), 0.32 * float(win.height) / float(sz.height))
                node.setScaleX(fit)
                node.setScaleY(fit)
        except:
            pass
    except:
        pass

def _dh_run_art_swap(name, ui):
    try:
        import cc
        # Ilagay ang ROS Redemption background sa PLAY screen
        if 'login' in name.lower() and not getattr(ui, '_has_redemption_bg', False):
            try:
                win = cc.Director.getInstance().getWinSize()
                bg = cc.Sprite.create('dh_brand/dh_bg1.jpg')
                if bg:
                    bg.setPosition(win.width / 2.0, win.height / 2.0)
                    sz = bg.getContentSize()
                    if sz.width > 0 and sz.height > 0:
                        bg.setScaleX(float(win.width) / float(sz.width))
                        bg.setScaleY(float(win.height) / float(sz.height))
                    ui.addChild(bg, -100)
                    ui._has_redemption_bg = True
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
                
                # Palitan ang Loading Screen Background
                if 'loading' in name.lower() and ('bg' in leaf or 'background' in leaf or 'pic' in leaf):
                    _dh_swap_tex(node, 'dh_brand/dh_bg1.jpg')

                # Palitan ang PLAY screen Logo mula ROS LEGACY -> ROS REDEMPTION!
                if 'login' in name.lower():
                    if 'bg' in leaf or 'background' in leaf:
                        _dh_swap_tex(node, 'dh_brand/dh_bg1.jpg')
                    if 'img_login_logo' in render or ('logo' in leaf and 'btn' not in leaf):
                        _dh_swap_logo(node, 'dh_brand/dh_logo_1.png')

                # Alisin ang SkyGame Website ribbon
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
                    if 'elect server' in t_low:
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
                for d in (0.0, 0.1, 0.3, 0.6, 1.2, 2.0, 3.5):
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
src += art_code

# Include Profile Rename & Country Flag Controls
profile_hook_path = os.path.join(base_dir, "profile_controls_hook.py")
if os.path.exists(profile_hook_path):
    with open(profile_hook_path, "r", encoding="utf-8") as pf:
        src += "\n\n" + pf.read()

for hf in [
    os.path.join(base_dir, "runtime", "app", "client", "lobby_hook.py"),
    r"C:\DieHardROS\runtime\app\client\lobby_hook.py"
]:
    try:
        os.makedirs(os.path.dirname(hf), exist_ok=True)
        with open(hf, "w", encoding="utf-8") as f:
            f.write(src)
        print("Updated hook at:", hf)
    except Exception as ex:
        pass

# Ensure server_patch.py is synced
sp_src = os.path.join(base_dir, "local_update", "hot", "server_patch.py")
if os.path.exists(sp_src):
    for sp_dst in [
        os.path.join(base_dir, "runtime", "app", "local_update", "hot", "server_patch.py"),
        os.path.join(base_dir, "ROS_Redemption_Server_Package", "local_update", "hot", "server_patch.py")
    ]:
        try:
            os.makedirs(os.path.dirname(sp_dst), exist_ok=True)
            shutil.copyfile(sp_src, sp_dst)
            print("Synced server_patch to:", sp_dst)
        except Exception:
            pass

print(">>> Hook, Server Patch, and Assets completely updated!")
