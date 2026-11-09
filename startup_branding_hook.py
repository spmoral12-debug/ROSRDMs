# Appended to the client lobby hook before injection (embedded Python 2.7).

def _set_ros_window_title():
    try:
        import ctypes
        import os
        user32 = ctypes.windll.user32
        target_title = u"ROS REDEMPTION"
        # 1. Direct search by known titles
        for name in (u"Rules of Survival 1.610660.519384", u"Rules of Survival", u"ROS", u"DieHard ROS", u"ROS Redemption 1.610660.519384", u"ROS Redemption"):
            try:
                h = user32.FindWindowW(None, name)
                if h:
                    user32.SetWindowTextW(h, target_title)
            except Exception:
                pass
        # 2. Enum all windows for current pid
        self_pid = os.getpid()
        def enum_cb(hwnd, extra):
            try:
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == self_pid and user32.IsWindowVisible(hwnd):
                    buf = ctypes.create_unicode_buffer(512)
                    user32.GetWindowTextW(hwnd, buf, 512)
                    txt = buf.value
                    if any(k in txt for k in (u"Rules of Survival", u"DieHard", u"ROS")):
                        if txt != target_title:
                            user32.SetWindowTextW(hwnd, target_title)
            except Exception:
                pass
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    except Exception:
        pass


def _redemption_patch_screen_tick(tick=0):
    import re
    _set_ros_window_title()
    try:
        import Globals
        manager = getattr(Globals, 'uiMgr', None)
        patch = _ui_open(manager, 'UIPatch') if manager is not None else None
        if patch is not None:
            for path, node in walk_ui_nodes(patch, limit=800):
                try:
                    path = path.strip('/').lower()
                    if path.endswith('ui_patch/bg'):
                        art = 'dh_brand/dh_redemption_loading.jpg'
                        get_file = getattr(node, 'getTextureFilename', None)
                        current = get_file() if callable(get_file) else None
                        loader = getattr(node, 'loadTexture', None) or getattr(node, 'setTexture', None)
                        if callable(loader) and art != current and (
                                current is not None or not getattr(patch, '_redemption_art_loaded', False)):
                            loader(art)
                            if not getattr(patch, '_redemption_art_loaded', False):
                                patch._redemption_art_loaded = True
                                log('local-redemption-patch-art', path=path)
                    text = _node_text(node)
                    if text and 'skygame.io' in text.lower():
                        setter = _node_setter(node)
                        if setter is not None:
                            updated = re.sub(r'(?:https?://)?(?:ros\.|www\.)?skygame\.io',
                                             'www.ros-redemption.com', text, flags=re.I)
                            if updated != text:
                                setter(updated)
                                if not getattr(patch, '_redemption_url_loaded', False):
                                    patch._redemption_url_loaded = True
                                    log('local-redemption-patch-website', path=path)
                except Exception:
                    pass
    except Exception:
        log_error('local-redemption-patch-screen-error')
    if tick < 400:
        call_later(0.15, _redemption_patch_screen_tick, tick + 1)
    else:
        call_later(1.0, _redemption_continuous_title_guard)


def _redemption_continuous_title_guard():
    _set_ros_window_title()
    call_later(1.0, _redemption_continuous_title_guard)


call_later(0.05, _redemption_patch_screen_tick)
