# Appended to the client lobby hook before injection (embedded Python 2.7).

def _set_ros_window_title():
    try:
        import ctypes
        import os
        user32 = ctypes.windll.user32
        target_title = u"ROS REDEMPTION"
        
        # Explicit 64-bit safe ctypes signatures to prevent HWND truncation
        user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.SetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        user32.SetWindowTextW.restype = ctypes.c_bool
        user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
        user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
        user32.IsWindowVisible.restype = ctypes.c_bool

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
                    if any(k in txt for k in (u"Rules of Survival", u"DieHard", u"ROS", u"1.610660")):
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
        _fix_season_labels_guard()
        call_later(0.15, _redemption_patch_screen_tick, tick + 1)
    else:
        call_later(0.5, _redemption_continuous_title_guard)


def _walk_fix_season(target, max_nodes=5000):
    if target is None:
        return 0
    try:
        import utils
        utils.getCurrentSeasonID = lambda *a, **k: 1
    except Exception:
        pass
    try:
        import rank_utils
        if hasattr(rank_utils, 'getCurrentSeasonID'):
            rank_utils.getCurrentSeasonID = lambda *a, **k: 1
    except Exception:
        pass
    import re
    seen = set()
    stack = [target]
    changed = 0
    while stack and len(seen) < max_nodes:
        curr = stack.pop()
        if curr is None:
            continue
        cid = id(curr)
        if cid in seen:
            continue
        seen.add(cid)

        # 1. Traverse Cocos2d-x children
        if hasattr(curr, 'getChildren'):
            try:
                ch = curr.getChildren()
                if ch:
                    stack.extend(list(ch))
            except Exception:
                pass

        # 2. Traverse Python wrapper attributes
        if hasattr(curr, '__dict__'):
            try:
                for k, v in curr.__dict__.items():
                    if v is not None:
                        if hasattr(v, 'getChildren') or hasattr(v, '__dict__'):
                            stack.append(v)
                        elif isinstance(v, (list, tuple)):
                            stack.extend(list(v))
                        elif isinstance(v, dict):
                            stack.extend(list(v.values()))
            except Exception:
                pass

        # 3. Traverse UITabView panels if present
        if hasattr(curr, 'getTabPanel'):
            for tab in ('record', 'mainpage', 'peiwan', 'intimate', 'credit', 'vip', 'marriage'):
                try:
                    p = curr.getTabPanel(tab)
                    if p is not None:
                        stack.append(p)
                except Exception:
                    pass

        # 4. Check text modification on current node
        getter = None
        setter = None
        if hasattr(curr, 'getTitleText') and hasattr(curr, 'setTitleText'):
            getter = getattr(curr, 'getTitleText')
            setter = getattr(curr, 'setTitleText')
        elif hasattr(curr, 'getString') and hasattr(curr, 'setString'):
            getter = getattr(curr, 'getString')
            setter = getattr(curr, 'setString')
        elif hasattr(curr, 'getText') and hasattr(curr, 'setText'):
            getter = getattr(curr, 'getText')
            setter = getattr(curr, 'setText')

        if callable(getter) and callable(setter):
            try:
                text = str(getter() or '')
            except Exception:
                text = ''
            if text:
                if 'Season 17' in text or 'Season17' in text:
                    try:
                        new_text = re.sub(r'\bSeason\s*17\b', 'Season 1', text)
                        setter(new_text)
                        changed += 1
                        continue
                    except Exception:
                        pass
                elif re.search(r'\bSeason\s*(1[0-6]|[2-9])\b', text):
                    try:
                        parent = curr.getParent() if hasattr(curr, 'getParent') else None
                        if parent is not None and hasattr(parent, 'getChildren') and len(list(parent.getChildren())) <= 4:
                            parent.setVisible(False)
                        else:
                            curr.setVisible(False)
                        changed += 1
                    except Exception:
                        pass
    return changed


def _hook_record_panel_class():
    try:
        import sys, re
        mod = sys.modules.get('ui.UIMeetMainPage')
        if not mod:
            try:
                mod = __import__('ui.UIMeetMainPage', fromlist=['UIBattleGroundRecordPanel'])
            except Exception:
                return
        cls = getattr(mod, 'UIBattleGroundRecordPanel', None)
        if cls and not getattr(cls, '_dh_season_hooked', False):
            cls._dh_season_hooked = True
            
            orig_get_ui = getattr(cls, '_get_ui', None)
            if orig_get_ui:
                def wrapped_get_ui(self, *a, **k):
                    res = orig_get_ui(self, *a, **k)
                    try:
                        btn = getattr(self, 'showModeSecondary', None)
                        if btn and hasattr(btn, 'setTitleText'):
                            btn.setTitleText('Season 1')
                        choose = getattr(self, 'modeChooseSecondary', None)
                        if choose:
                            _walk_fix_season(choose)
                    except Exception:
                        pass
                    return res
                cls._get_ui = wrapped_get_ui
                
            orig_show_sec = getattr(cls, 'onShowModeSecondaryClick', None)
            if orig_show_sec:
                def wrapped_show_sec(self, *a, **k):
                    res = orig_show_sec(self, *a, **k)
                    try:
                        choose = getattr(self, 'modeChooseSecondary', None)
                        if choose:
                            _walk_fix_season(choose)
                    except Exception:
                        pass
                    return res
                cls.onShowModeSecondaryClick = wrapped_show_sec

            orig_game_sec = getattr(cls, 'onGameModeSecondaryClick', None)
            if orig_game_sec:
                def wrapped_game_sec(self, *a, **k):
                    res = orig_game_sec(self, *a, **k)
                    try:
                        btn = getattr(self, 'showModeSecondary', None)
                        if btn and hasattr(btn, 'getTitleText') and hasattr(btn, 'setTitleText'):
                            t = btn.getTitleText()
                            if '17' in t:
                                btn.setTitleText(t.replace('17', '1'))
                    except Exception:
                        pass
                    return res
                cls.onGameModeSecondaryClick = wrapped_game_sec
    except Exception:
        pass


def _fix_season_labels_guard():
    _hook_record_panel_class()
    try:
        import Globals, re
        ui_mgr = getattr(Globals, 'uiMgr', None)
        if ui_mgr is not None:
            all_ui = getattr(ui_mgr, '____all_ui__', None) or {}
            for name, ui in all_ui.items():
                if ui is None:
                    continue
                if name == 'UIMeetMainPage':
                    for attr in ('battleGroundRecordPanel', 'recordPanel', '_battleGroundRecordPanel'):
                        p = getattr(ui, attr, None)
                        if p is not None:
                            btn = getattr(p, 'showModeSecondary', None)
                            if btn is not None and hasattr(btn, 'getTitleText') and hasattr(btn, 'setTitleText'):
                                t = btn.getTitleText()
                                if '17' in t:
                                    btn.setTitleText(re.sub(r'\bSeason\s*17\b', 'Season 1', t))
                            choose = getattr(p, 'modeChooseSecondary', None)
                            if choose is not None:
                                _walk_fix_season(choose)
                    w = getattr(ui, 'widget', None) or ui
                    _walk_fix_season(w)
                elif hasattr(ui, 'widget'):
                    _walk_fix_season(ui.widget)
    except Exception:
        pass


def _redemption_continuous_title_guard():
    _set_ros_window_title()
    _fix_season_labels_guard()
    call_later(0.5, _redemption_continuous_title_guard)


call_later(0.05, _redemption_patch_screen_tick)
