# -*- coding: utf-8 -*-
import os

target_files = [
    r'clean_remote_lobby.py',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py'
]

new_window_title_loop = """_dh_f5_cooldown = [0.0]

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
                ln = sc.getChildByName('UILogin')
                if ln is None or not ln.isVisible() or _dh_in_lobby():
                    b = sc.getChildByName('ros_redemption_bg')
                    if b is not None:
                        b.removeFromParent()
                if _dh_in_lobby():
                    import Globals
                    main = getattr(Globals.uiMgr, 'UIMain', None)
                    if main is not None:
                        _dh_bind_top_tabs(main)
    except Exception:
        pass
    call_later(0.2, _dh_window_title_loop)

call_later(0.05, _dh_window_title_loop)
"""

for file_path in target_files:
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        idx = content.find('def _dh_window_title_loop():')
        if idx != -1:
            content = content[:idx] + new_window_title_loop
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print("Successfully updated window title & ranking loop in:", file_path)
        else:
            print("def _dh_window_title_loop(): not found in:", file_path)
    else:
        print("File does not exist:", file_path)
