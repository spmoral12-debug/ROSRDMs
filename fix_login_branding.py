# -*- coding: utf-8 -*-
import os

target_files = [
    r'clean_remote_lobby.py',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py'
]

replacement_brand_pass_head = """def _dh_scene_brand_pass():
    cc = _dh_cc()
    if cc is None:
        return
    scene = cc.Director.getInstance().getRunningScene()
    if scene is None:
        return

    # In lobby or in battle: remove wallpaper so 3D lobby, room, and character are clean
    if _dh_in_lobby() or _dh_in_battle():
        try:
            bg = scene.getChildByName('ros_redemption_bg')
            if bg is not None:
                bg.removeFromParent()
        except Exception:
            pass
        return

    # Strictly on Login / Play screen:
    # 1. Attach ROS Redemption HD Wallpaper (with the epic 3D winged logo)
    try:
        bg_path = 'dh_brand/dh_bg1.jpg'
        win = cc.Director.getInstance().getWinSize()
        bg = scene.getChildByName('ros_redemption_bg')
        if bg is None:
            bg = cc.Sprite.create(bg_path)
            if bg is not None:
                bg.setName('ros_redemption_bg')
                bg.setPosition(win.width / 2.0, win.height / 2.0)
                sz = bg.getContentSize()
                if sz.width > 0 and sz.height > 0:
                    bg.setScaleX(float(win.width) / float(sz.width))
                    bg.setScaleY(float(win.height) / float(sz.height))
                scene.addChild(bg, 50)
    except Exception:
        pass

    """

replacement_loop = """_dh_f5_cooldown = [0.0]

def _dh_window_title_loop():
    _dh_set_window_title_redemption()
    try:    
        import ctypes, time
        now = time.time()
        # F5 Keyboard Hotkey for Instant Leaderboard / Ranking Board
        if (ctypes.windll.user32.GetAsyncKeyState(0x74) & 0x8000) and (now - _dh_f5_cooldown[0] > 0.5):
            _dh_f5_cooldown[0] = now
            try:
                import Globals
                Globals.uiMgr.enter_ui('UIRankList')
                print(">>> [ROS REDEMPTION] F5 Pressed: Opened UIRankList Leaderboard!")
            except Exception as e:
                print(">>> [ROS REDEMPTION] F5 Error: " + repr(e))
    except Exception:
        pass

    try:
        cc = _dh_cc()
        if cc is not None:
            sc = cc.Director.getInstance().getRunningScene()
            if sc is not None:
                if _dh_in_lobby() or _dh_in_battle():
                    # Clean lobby: Remove wallpaper
                    b = sc.getChildByName('ros_redemption_bg')
                    if b is not None:
                        b.removeFromParent()
                    import Globals
                    main = getattr(Globals.uiMgr, 'UIMain', None)
                    if main is not None:
                        _dh_bind_top_tabs(main)
                else:
                    # On Login / Play screen: Ensure wallpaper is visible
                    b = sc.getChildByName('ros_redemption_bg')
                    if b is None:
                        win = cc.Director.getInstance().getWinSize()
                        b = cc.Sprite.create('dh_brand/dh_bg1.jpg')
                        if b is not None:
                            b.setName('ros_redemption_bg')
                            b.setPosition(win.width / 2.0, win.height / 2.0)
                            sz = b.getContentSize()
                            if sz.width > 0 and sz.height > 0:
                                b.setScaleX(float(win.width) / float(sz.width))
                                b.setScaleY(float(win.height) / float(sz.height))
                            sc.addChild(b, 50)
    except Exception:
        pass
    call_later(0.2, _dh_window_title_loop)

call_later(0.05, _dh_window_title_loop)
"""

for file_path in target_files:
    if not os.path.exists(file_path):
        print("Skipping non-existent:", file_path)
        continue

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()

    # 1. Replace _dh_scene_brand_pass head
    idx_start = text.find('def _dh_scene_brand_pass():')
    idx_hide = text.find('# --- ROS Redemption: hide street squad')
    if idx_start != -1 and idx_hide != -1 and idx_start < idx_hide:
        text = text[:idx_start] + replacement_brand_pass_head + text[idx_hide:]
        print("Updated _dh_scene_brand_pass in:", file_path)
    else:
        print("Could not locate _dh_scene_brand_pass in:", file_path)

    # 2. Replace _dh_window_title_loop
    idx_loop = text.find('def _dh_window_title_loop():')
    if idx_loop != -1:
        # Check if _dh_f5_cooldown is right before it
        idx_f5 = text.rfind('_dh_f5_cooldown', 0, idx_loop)
        cut_point = idx_f5 if idx_f5 != -1 and (idx_loop - idx_f5) < 100 else idx_loop
        text = text[:cut_point] + replacement_loop
        print("Updated _dh_window_title_loop in:", file_path)
    else:
        print("Could not locate _dh_window_title_loop in:", file_path)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(text)

print("Done updating files!")

