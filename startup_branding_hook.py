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


def _dh_patch_whitelist_stub():
    try:
        import sys
        dummy = lambda *a, **k: {}
        for mod in list(sys.modules.values()):
            if mod is not None and not hasattr(mod, 'getAppearanceWhitelistData'):
                try:
                    setattr(mod, 'getAppearanceWhitelistData', dummy)
                except Exception:
                    pass
        for mod_name in ('tables', 'tables.tables', 'dts_appearance_preload', 'dts_hall_prop_utils',
                         'helpers.character_scene', 'helpers.character_scene.legacyProperties',
                         'shared.lib.gametoolslib.properties', 'logic.gamedata.tables'):
            try:
                m = __import__(mod_name, fromlist=['getAppearanceWhitelistData'])
                if not hasattr(m, 'getAppearanceWhitelistData'):
                    setattr(m, 'getAppearanceWhitelistData', dummy)
            except Exception:
                pass
    except Exception:
        pass


def _dh_patch_uimain_visibilities():
    try:
        from ui.UIMain import UIMain
        orig_vis = getattr(UIMain, '_dh_orig_init_vis', getattr(UIMain, '_init_ui_visibilities', None))
        if callable(orig_vis):
            UIMain._dh_orig_init_vis = orig_vis
            def _safe_init_ui_visibilities(self, *a, **k):
                try:
                    return orig_vis(self, *a, **k)
                except TypeError:
                    pass
                except Exception:
                    pass
            UIMain._init_ui_visibilities = _safe_init_ui_visibilities
    except Exception:
        pass


_dh_patch_whitelist_stub()
_dh_patch_uimain_visibilities()


def _fix_button_or_node_season(node):
    if node is None:
        return
    import re
    stack = [node]
    seen = set()
    while stack:
        curr = stack.pop()
        if curr is None:
            continue
        cid = id(curr)
        if cid in seen:
            continue
        seen.add(cid)
        if hasattr(curr, 'getChildren'):
            try:
                for c in list(curr.getChildren() or []):
                    stack.append(c)
            except Exception:
                pass
        if hasattr(curr, 'getTitleRenderer'):
            try:
                tr = curr.getTitleRenderer()
                if tr:
                    stack.append(tr)
            except Exception:
                pass
        for g_name, s_name in (('getTitleText', 'setTitleText'),
                               ('getString', 'setString'),
                               ('getText', 'setText')):
            if hasattr(curr, g_name) and hasattr(curr, s_name):
                try:
                    val = getattr(curr, g_name)()
                    if val is not None:
                        is_uni = isinstance(val, unicode)
                        s = val if is_uni else str(val).decode('utf-8', 'ignore')
                        if '17' in s:
                            s2 = re.sub(r'\bSeason\s*17\b', u'Season 1', s)
                            s2 = re.sub(r'Season17', u'Season 1', s2)
                            s2 = re.sub(r'17', u'1', s2)
                            getattr(curr, s_name)(s2 if is_uni else s2.encode('utf-8'))
                        elif re.search(r'\bSeason\s*(1[0-6]|[2-9])\b', s):
                            parent = curr.getParent() if hasattr(curr, 'getParent') else None
                            if parent and hasattr(parent, 'getChildren') and len(list(parent.getChildren() or [])) <= 4:
                                parent.setVisible(False)
                            elif hasattr(curr, 'setVisible'):
                                curr.setVisible(False)
                except Exception:
                    pass


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
    _fix_button_or_node_season(target)
    return 1


def _hook_record_panel_class():
    try:
        import sys, re
        mod = sys.modules.get('ui.UIMeetMainPage')
        if not mod:
            try:
                mod = __import__('ui.UIMeetMainPage', fromlist=['UIBattleGroundRecordPanel', 'UIMeetMainPage'])
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
                        if btn:
                            _fix_button_or_node_season(btn)
                        choose = getattr(self, 'modeChooseSecondary', None)
                        if choose:
                            _fix_button_or_node_season(choose)
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
                            _fix_button_or_node_season(choose)
                        btn = getattr(self, 'showModeSecondary', None)
                        if btn:
                            _fix_button_or_node_season(btn)
                    except Exception:
                        pass
                    return res
                cls.onShowModeSecondaryClick = wrapped_show_sec

            orig_set_choose = getattr(cls, '_setModeSecondaryChoose', None)
            if orig_set_choose:
                def wrapped_set_choose(self, *a, **k):
                    res = orig_set_choose(self, *a, **k)
                    try:
                        choose = getattr(self, 'modeChooseSecondary', None)
                        if choose:
                            _fix_button_or_node_season(choose)
                        btn = getattr(self, 'showModeSecondary', None)
                        if btn:
                            _fix_button_or_node_season(btn)
                    except Exception:
                        pass
                    return res
                cls._setModeSecondaryChoose = wrapped_set_choose

            orig_game_sec = getattr(cls, 'onGameModeSecondaryClick', None)
            if orig_game_sec:
                def wrapped_game_sec(self, *a, **k):
                    res = orig_game_sec(self, *a, **k)
                    try:
                        btn = getattr(self, 'showModeSecondary', None)
                        if btn:
                            _fix_button_or_node_season(btn)
                    except Exception:
                        pass
                    return res
                cls.onGameModeSecondaryClick = wrapped_game_sec

            orig_resp = getattr(cls, 'responseToClickGameMode', None)
            if orig_resp:
                def wrapped_resp(self, *a, **k):
                    res = orig_resp(self, *a, **k)
                    try:
                        btn = getattr(self, 'showModeSecondary', None)
                        if btn:
                            _fix_button_or_node_season(btn)
                    except Exception:
                        pass
                    return res
                cls.responseToClickGameMode = wrapped_resp
    except Exception:
        pass


def _hook_submodes_class():
    try:
        import sys
        for mod_name, mod in list(sys.modules.items()):
            if mod is not None:
                try:
                    if not hasattr(mod, 'I_GOLD_BATTLE_NEW_YEAR_BASE_TIME'):
                        setattr(mod, 'I_GOLD_BATTLE_NEW_YEAR_BASE_TIME', 0)
                except Exception:
                    pass
        smod = sys.modules.get('ui.UISubModesEnter')
        if not smod:
            try:
                smod = __import__('ui.UISubModesEnter', fromlist=['UISubModesEnter', 'UIModesList'])
            except Exception:
                return
        if smod:
            if not hasattr(smod, 'I_GOLD_BATTLE_NEW_YEAR_BASE_TIME'):
                setattr(smod, 'I_GOLD_BATTLE_NEW_YEAR_BASE_TIME', 0)
            for attr_name, val in list(vars(smod).items()):
                if isinstance(val, dict):
                    if 'RosTopia' not in val:
                        val['RosTopia'] = lambda *a, **k: None
                    if 'rostopia' not in val:
                        val['rostopia'] = lambda *a, **k: None

            for cls_name, cls in list(vars(smod).items()):
                if isinstance(cls, (type, type(object))) or type(cls).__name__ == 'classobj':
                    if hasattr(cls, '_initGoldBattlePanel'):
                        orig_g = getattr(cls, '_initGoldBattlePanel')
                        if orig_g and not getattr(orig_g, '_dh_guarded', False):
                            def _safe_g(self, *a, **k):
                                try:
                                    return orig_g(self, *a, **k)
                                except Exception:
                                    return None
                            _safe_g._dh_guarded = True
                            setattr(cls, '_initGoldBattlePanel', _safe_g)

                    if hasattr(cls, 'onConfirmEvent'):
                        orig_c = getattr(cls, 'onConfirmEvent')
                        if orig_c and not getattr(orig_c, '_dh_guarded', False):
                            def _safe_c(self, *a, **k):
                                try:
                                    for dname in dir(self):
                                        try:
                                            dval = getattr(self, dname, None)
                                            if isinstance(dval, dict):
                                                if 'RosTopia' not in dval:
                                                    dval['RosTopia'] = lambda *x, **y: None
                                                if 'rostopia' not in dval:
                                                    dval['rostopia'] = lambda *x, **y: None
                                        except Exception:
                                            pass
                                    return orig_c(self, *a, **k)
                                except Exception:
                                    try:
                                        import Globals
                                        Globals.uiMgr.leave_ui('UISubModesEnter')
                                    except Exception:
                                        pass
                                    try:
                                        if hasattr(self, 'close'):
                                            self.close()
                                    except Exception:
                                        pass
                                    return None
                            _safe_c._dh_guarded = True
                            setattr(cls, 'onConfirmEvent', _safe_c)

                    if hasattr(cls, 'onCancelEvent'):
                        orig_cancel = getattr(cls, 'onCancelEvent')
                        if orig_cancel and not getattr(orig_cancel, '_dh_guarded', False):
                            def _safe_cancel(self, *a, **k):
                                try:
                                    orig_cancel(self, *a, **k)
                                except Exception:
                                    pass
                                try:
                                    import Globals
                                    Globals.uiMgr.leave_ui('UISubModesEnter')
                                except Exception:
                                    pass
                                try:
                                    if hasattr(self, 'close'):
                                        self.close()
                                except Exception:
                                    pass
                            _safe_cancel._dh_guarded = True
                            setattr(cls, 'onCancelEvent', _safe_cancel)
    except Exception:
        pass


def _fix_season_labels_guard():
    _dh_patch_whitelist_stub()
    _dh_patch_uimain_visibilities()
    _hook_record_panel_class()
    _hook_submodes_class()
    try:
        import Globals
        ui_mgr = getattr(Globals, 'uiMgr', None)
        if ui_mgr is not None:
            all_ui = getattr(ui_mgr, '____all_ui__', None) or {}
            for name, ui in all_ui.items():
                if ui is None:
                    continue
                if name == 'UIMeetMainPage':
                    mt = getattr(ui, '_mainTab', None) or ui
                    rec = None
                    if hasattr(mt, 'getTabPanel'):
                        try:
                            rec = mt.getTabPanel('record')
                        except Exception:
                            pass
                    panels = [p for p in (rec, getattr(ui, 'battleGroundRecordPanel', None), getattr(ui, 'recordPanel', None)) if p is not None]
                    for p in panels:
                        _fix_button_or_node_season(getattr(p, 'showModeSecondary', None))
                        _fix_button_or_node_season(getattr(p, 'modeChooseSecondary', None))
                        _fix_button_or_node_season(p)
                    w = getattr(ui, 'widget', None) or ui
                    _fix_button_or_node_season(w)
                elif hasattr(ui, 'widget'):
                    _fix_button_or_node_season(ui.widget)
    except Exception:
        pass


def _redemption_continuous_title_guard():
    _set_ros_window_title()
    _fix_season_labels_guard()
    call_later(0.5, _redemption_continuous_title_guard)


call_later(0.05, _redemption_patch_screen_tick)
