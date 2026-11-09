import os
import py_compile

src_path = r"c:\Users\seanj\dev\lobby_hook_unsealed.py"
dst_path = r"C:\DieHardROS\runtime\app\client\lobby_hook.py"

with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
    code = f.read()

# 1. Clean up legacy / DieHard branding strings
replacements = [
    ("ros.skygame.io", ""),
    ("Official website:", ""),
    ("Official website", ""),
    ("DieHard ROS Online", "ROS Redemption"),
    ("DieHard ROS", "ROS Redemption"),
    ("DieHard", "ROS Redemption"),
    ("roslegacy.net", ""),
    ("ROS LEGACY", "ROS REDEMPTION"),
    ("ros legacy", "ROS Redemption"),
    ("roslegacy", "ROS Redemption"),
    ("http://172.16.69.27/topup", "http://127.0.0.1:8888"),
]
for old, rep in replacements:
    code = code.replace(old, rep)

# 2. Update DH_BRAND_TEXT tuple
code = code.replace(
    "('legacy', 'DieHard')",
    "('legacy', 'ROS Redemption'), ('diehard', 'ROS Redemption')"
)

# 3. Default economy in profile (100k diamonds, 500k gold)
code = code.replace(
    "'gp': player_state.get('gp', 0),",
    "'gp': player_state.get('gp', 0) or 500000,"
)
code = code.replace(
    "'freeYuanbao': player_state.get('freeYuanbao', 0),",
    "'freeYuanbao': player_state.get('freeYuanbao', 0) or 100000,"
)
code = code.replace(
    "'payYuanbao': player_state.get('payYuanbao', 0),",
    "'payYuanbao': player_state.get('payYuanbao', 0) or 100000,"
)

# 4. Master Branding, 64-bit Title/Icon & Server Fix
art_and_server_fix = '''

# --------------------------------------------------------------------------
# ROS REDEMPTION: 64-BIT WINDOW TITLE/ICON, BACKGROUND & SERVER BRANDING
# --------------------------------------------------------------------------

def set_ros_redemption_window():
    try:
        import ctypes
        import sys
        user32 = ctypes.windll.user32
        target_title = u"ROS Redemption 1.610660.519384"
        icon_path = os.path.abspath(r"C:\\DieHardROS\\ros_redemption.ico")

        # 1. Find window by known ROS titles first
        for name in (u"Rules of Survival 1.610660.519384", u"Rules of Survival", u"ROS", u"DieHard ROS"):
            try:
                h = user32.FindWindowW(None, name)
                if h:
                    user32.SetWindowTextW(h, target_title)
                    _apply_hicon(user32, h, icon_path)
            except Exception:
                pass

        # 2. 64-bit safe EnumWindows
        def enum_cb(hwnd, extra):
            try:
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == os.getpid() and user32.IsWindowVisible(hwnd):
                    buf = ctypes.create_unicode_buffer(512)
                    user32.GetWindowTextW(hwnd, buf, 512)
                    txt = buf.value
                    if u"Rules of Survival" in txt or u"DieHard" in txt or txt == u"" or u"ROS" in txt:
                        user32.SetWindowTextW(hwnd, target_title)
                        _apply_hicon(user32, hwnd, icon_path)
            except Exception:
                pass
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    except Exception:
        pass


def _apply_hicon(user32, hwnd, icon_path):
    try:
        if os.path.exists(icon_path):
            path_arg = unicode(icon_path) if sys.version_info[0] < 3 else str(icon_path)
            hicon_big = user32.LoadImageW(0, path_arg, 1, 48, 48, 0x0010)
            hicon_sm = user32.LoadImageW(0, path_arg, 1, 16, 16, 0x0010)
            if hicon_big:
                user32.SendMessageW(hwnd, 0x0080, 1, hicon_big)
            if hicon_sm:
                user32.SendMessageW(hwnd, 0x0080, 0, hicon_sm)
    except Exception:
        pass


def _dh_swap_tex(node, rel):
    try:
        import cc
        tex = cc.Director.getInstance().getTextureCache().addImage(rel)
        if hasattr(node, 'loadTexture'):
            try:
                node.loadTexture(rel, 0)
            except Exception:
                node.loadTexture(rel)
        elif hasattr(node, 'setTexture') and tex:
            node.setTexture(tex)
    except Exception:
        pass


def _dh_apply_screen_branding(name, ui):
    if ui is None:
        return
    try:
        # Force official server values on UI object
        try:
            setattr(ui, '_currentSelectServerName', 'ROS-Redemption-Official')
            setattr(ui, '_currentSelectGroupId', 10501)
            setattr(ui, '_currentSelectServerIp', '127.0.0.1')
            setattr(ui, '_currentSelectServerPort', 19000)
            setattr(ui, '_currentSelectZoneName', 'ROS-Redemption')
        except Exception:
            pass

        # 1. Full-screen ROS Redemption Wallpaper on Cocos2D panel
        panel = getattr(ui, 'panel', None)
        if panel is not None and not getattr(ui, '_has_redemption_bg', False):
            try:
                import cc
                win = cc.Director.getInstance().getWinSize()
                bg = cc.Sprite.create('dh_brand/dh_bg1.jpg')
                if bg:
                    bg.setPosition(win.width / 2.0, win.height / 2.0)
                    sz = bg.getContentSize()
                    if sz.width > 0 and sz.height > 0:
                        bg.setScaleX(float(win.width) / float(sz.width))
                        bg.setScaleY(float(win.height) / float(sz.height))
                    panel.addChild(bg, -999)
                    ui._has_redemption_bg = True
            except Exception:
                pass

        # 2. Iterate all widgets
        for path, node in walk_ui_nodes(ui, limit=1200):
            try:
                p_low = path.lower()
                leaf = path.split('/')[-1].lower()

                # Hide old animated squad/street layers, QR code, Facebook
                if any(k in p_low for k in ('layer_swing', 'qrcode', 'facebook', 'icon_facebook', 'bg_login_word', 'vng_logo')):
                    try:
                        node.setVisible(False)
                    except Exception:
                        pass
                    continue

                render = ''
                for g in ('getRenderFile', 'getTextureFile', 'getBackGroundImageFile'):
                    fn = getattr(node, g, None)
                    if callable(fn):
                        try:
                            render = str(fn()).lower()
                            break
                        except Exception:
                            pass

                # Swap Logo to ROS Redemption 3D metallic logo
                if 'logo' in leaf and 'btn' not in leaf and 'icon' not in leaf:
                    _dh_swap_tex(node, 'txt_logo_zjzc.png')

                # Background textures
                if 'bg' in leaf or 'background' in leaf or 'bg_loading' in render:
                    _dh_swap_tex(node, 'dh_brand/dh_bg1.jpg')

                # Server List & Zone text rebranding
                text = _node_text(node)
                setter = _node_setter(node)
                if text:
                    t_low = text.lower()
                    if any(k in t_low for k in ('skygame', 'official website', 'ros.skygame.io', 'dicord', 'discord')):
                        try:
                            node.setVisible(False)
                            p = node.getParent()
                            if p: p.setVisible(False)
                        except Exception:
                            pass
                        if setter: setter('')
                    elif any(k in t_low for k in ('ph-diehard', 'my-asia', 'pc-asia', 'diehard', 'legacy', 'pc-manila', 'pc-singapore', 'pc-tokyo', 'pc-sandbox')):
                        if setter: setter('ROS-Redemption-Official')
                    elif t_low in ('asia', 'america', 'europe', 'north america', 'pc', 'pc-america', 'pc-europe'):
                        if setter: setter('ROS-Redemption')
                    elif 'select server' in t_low or 'elect server' in t_low:
                        if setter: setter('ROS-Redemption-Official')
            except Exception:
                pass
    except Exception:
        pass


def _dh_check_login_screens():
    set_ros_redemption_window()
    try:
        import Globals
        ui_mgr = getattr(Globals, 'uiMgr', None)
        if ui_mgr is not None:
            login = _ui_open(ui_mgr, 'UILogin')
            if login is not None:
                _dh_apply_screen_branding('UILogin', login)
            server_list = _ui_open(ui_mgr, 'UIServerList')
            if server_list is not None:
                _dh_apply_screen_branding('UIServerList', server_list)
            loading = _ui_open(ui_mgr, 'UILoading')
            if loading is not None:
                _dh_apply_screen_branding('UILoading', loading)
    except Exception:
        pass
    call_later(0.2, _dh_check_login_screens)

try:
    call_later(0.5, _dh_check_login_screens)
except Exception:
    pass
'''

code += art_and_server_fix

# Write to destination
with open(dst_path, "w", encoding="utf-8") as f:
    f.write(code)

print("Written to:", dst_path)

# Compile to test syntax
py_compile.compile(dst_path, doraise=True)
print("SUCCESS: lobby_hook.py syntax verified and compiled cleanly!")
