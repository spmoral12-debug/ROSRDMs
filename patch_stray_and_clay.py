# -*- coding: utf-8 -*-
import sys, os

def run_patch():
    with open('clean_remote_lobby.py', 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    new_block_1 = '''    # Clean native backdrop passthroughs:
    # When inspecting Firearms, Vehicles, or Clothes in Depot: hides backdrops so dark smoke showroom renders cleanly.
    # When in UIMain (main lobby): ALWAYS ensure sky and backdrop planes are visible, preventing pitch black sky and clay floor!
    def _dh_show_lobby_backdrop_safe(show):
        try:
            import BigWorld
            player = BigWorld.player()
            hall = getattr(player, 'hallScene', None) if player else None
            scene = getattr(hall, '_native_scene', None) if hall else None
            if scene is None:
                return 0
            
            # Reset retirement tracking when showing lobby
            if show:
                _lobby['native_hall_models'] = []
                _lobby['retired_hall_models'] = []
                _lobby['backdrop_hidden'] = False
            else:
                _lobby['backdrop_hidden'] = True

            changed = 0
            for model, name in scene_models(scene):
                name_lower = str(name).lower()
                is_bg = is_backdrop_name(name) or any(k in name_lower for k in ('plane_bg', 'sky', 'mountain', 'road', 'city', 'building', 'terrain'))
                if not is_bg:
                    continue

                # The offline motor vehicle should always stay hidden in lobby
                if 'motor' in name_lower or 'plane_motor' in name_lower:
                    try:
                        if getattr(model, 'visible', False):
                            model.visible = False
                            changed += 1
                    except Exception:
                        pass
                    continue

                try:
                    vis = bool(show)
                    if bool(getattr(model, 'visible', False)) != vis:
                        model.visible = vis
                        changed += 1
                except Exception:
                    continue
            return changed
        except Exception:
            return 0
    show_lobby_backdrop = _dh_show_lobby_backdrop_safe
    globals()['show_lobby_backdrop'] = _dh_show_lobby_backdrop_safe

    # Neutralize ensure_self_model for existing players:
    # The male creation dummy (SHOW_MODEL_PATH) must only ever appear on UISelectCharacter for brand new accounts!
    _dh_orig_ensure_self_model = globals().get('ensure_self_model')
    def _dh_safe_ensure_self_model(main_ui):
        try:
            saved = saved_character() if callable(globals().get('saved_character')) else None
            if saved is not None:
                return
            import BigWorld
            p = BigWorld.player()
            if p is not None and (getattr(p, 'nickname', None) or getattr(p, 'baseNickname', None)):
                return
        except Exception:
            pass
        if callable(_dh_orig_ensure_self_model):
            return _dh_orig_ensure_self_model(main_ui)
    ensure_self_model = _dh_safe_ensure_self_model
    globals()['ensure_self_model'] = _dh_safe_ensure_self_model

    # Wrap HallTheme._clearOldTheme so a destroyed space object from battle never aborts theme creation
    try:
        import sys
        for mod_name in ('ui.main.HallTheme', 'HallTheme'):
            mod = sys.modules.get(mod_name)
            cls = getattr(mod, 'HallTheme', None) if mod is not None else None
            if cls is not None:
                orig_c = getattr(cls, '_clearOldTheme', None)
                if callable(orig_c) and not getattr(orig_c, '_dh_safe_clear', False):
                    def _dh_safe_clear_old(self, *a, **k):
                        try:
                            return orig_c(self, *a, **k)
                        except Exception:
                            return None
                    _dh_safe_clear_old._dh_safe_clear = True
                    cls._clearOldTheme = _dh_safe_clear_old
    except Exception:
        pass

    # Periodic Lobby 3D Scene loop: maintains equipped lobby theme on UIMain,
    # unhides sky and environment planes, and purges stray male creation dummy models
    _dh_theme_switching = [False]
    def _dh_lobby_scene_watchdog():
        try:
            if _dh_in_lobby():
                import Globals, BigWorld
                ui_mgr = getattr(Globals, 'uiMgr', None)
                _inspecting = False
                if ui_mgr is not None:
                    _inspect_screens = (
                        'UIDtsAppearanceVehicle', 'UIDtsAppearanceWeapon', 'UIDtsAppearanceCostume',
                        'UIDtsAppearanceOthers', 'UIDtsAppearancePet', 'UIDtsAppearanceRole',
                        'UIDtsAppearance', 'UIDtsAppearanceNewAdded', 'UIDtsAppearanceVehicleCultivate2',
                        'UIWorkshop', 'UIItemDisplay', 'UIMallController', 'UIMall', 'UIMallCloth',
                        'UISupplyController', 'UISupplyPackage', 'UIAdvanceSupplyPackage'
                    )
                    for sname in _inspect_screens:
                        scr = getattr(ui_mgr, sname, None)
                        if scr is not None:
                            is_ent = getattr(scr, 'is_enter', False)
                            if callable(is_ent):
                                is_ent = is_ent()
                            is_vis = getattr(scr, 'isVisible', None)
                            if callable(is_vis):
                                is_vis = is_vis()
                            else:
                                is_vis = getattr(scr, 'visible', False)
                            if is_ent or is_vis:
                                _inspecting = True
                                break

                player = BigWorld.player() if 'BigWorld' in globals() or BigWorld is not None else None
                hall = getattr(player, 'hallScene', None) if player else None
                scene = getattr(hall, '_native_scene', None) if hall else None
                main_ui = getattr(ui_mgr, 'UIMain', None) if ui_mgr else None

                # Purge stray male creation model from UIMain and scene
                if main_ui and player:
                    is_female = False
                    try:
                        c_type = player.getCharacterType() if hasattr(player, 'getCharacterType') else getattr(player, 'characterType', 0)
                        data = character_data(c_type) if callable(globals().get('character_data')) else None
                        if int(getattr(data, 'GENDER', 1) or 1) == 2 or 'female' in str(getattr(player, 'nickname', '')).lower():
                            is_female = True
                    except Exception:
                        pass
                    
                    m_dict = getattr(main_ui, 'models', None)
                    if isinstance(m_dict, dict):
                        for gk, entry in list(m_dict.items()):
                            m = entry.get('model') if isinstance(entry, dict) else entry
                            if m is not None and m is not getattr(hall, 'model', None):
                                m_fn = str(getattr(m, 'filename', '')).lower()
                                if 'dataosha_male' in m_fn or 'male.gim' in m_fn or 'male_show_new' in m_fn:
                                    if is_female or gk not in _team_gids(player):
                                        try:
                                            m.visible = False
                                        except Exception:
                                            pass
                                        try:
                                            destroy_model(m)
                                        except Exception:
                                            pass
                                        m_dict.pop(gk, None)

                # Only manage theme and scene backdrop when player is in the main lobby, NOT inspecting!
                if not _inspecting and scene is not None:
                    # Unhide sky and backdrop planes in UIMain
                    for model, name in scene_models(scene):
                        name_lower = str(name).lower()
                        if any(k in name_lower for k in ('plane_bg', 'sky', 'mountain', 'road', 'city', 'building', 'terrain')):
                            if 'motor' not in name_lower and not getattr(model, 'visible', False):
                                try:
                                    model.visible = True
                                except Exception:
                                    pass

                    if player is not None and not _dh_theme_switching[0]:
                        own = _dh_theme_own()
                        target_theme = own if own else 279008
                        cur_theme = int(getattr(player, 'dtsHallThemeID', 0) or 0)
                        if cur_theme != target_theme:
                            _dh_theme_switching[0] = True
                            BigWorld._dh_theme_suspended = False
                            player.dtsHallThemeID = target_theme
                            if hasattr(player, 'onUpdateDtsHallThemeID'):
                                try:
                                    player.onUpdateDtsHallThemeID(target_theme)
                                except Exception:
                                    pass
                            call_later(5.0, lambda: _dh_theme_switching.__setitem__(0, False))
        except Exception:
            pass
        call_later(2.0, _dh_lobby_scene_watchdog)

    call_later(1.0, _dh_lobby_scene_watchdog)
except Exception:
    log_error('local-lobby-scene-safeguard-error')



# ---------------------------------------------------------------------
# Post-Battle Lobby Party & Teammate 3D Model Restoration
# ---------------------------------------------------------------------
_dh_party_restore = globals().get('_dh_party_restore') or {
    'leaving': False,
    'pending_enter': None,
    'last_enter': None,
    'last_enter_at': 0.0,
}


def _dh_ui_main_models():
    """Return all 3D character models currently managed by UIMain (self + teammates)."""
    kept = []
    try:
        import Globals, BigWorld
        player = BigWorld.player()
        is_female = False
        try:
            c_type = player.getCharacterType() if hasattr(player, 'getCharacterType') else getattr(player, 'characterType', 0)
            data = character_data(c_type) if callable(globals().get('character_data')) else None
            if int(getattr(data, 'GENDER', 1) or 1) == 2 or 'female' in str(getattr(player, 'nickname', '')).lower():
                is_female = True
        except Exception:
            pass

        main_ui = getattr(getattr(Globals, 'uiMgr', None), 'UIMain', None)
        if main_ui is None:
            return kept
        models_dict = getattr(main_ui, 'models', None)
        if isinstance(models_dict, dict):
            for gid_k, entry in models_dict.items():
                m = entry.get('model') if isinstance(entry, dict) else entry
                if m is not None:
                    # Never keep stray male creation model for female player
                    if is_female:
                        m_fn = str(getattr(m, 'filename', '')).lower()
                        if 'dataosha_male' in m_fn or 'male.gim' in m_fn or 'male_show_new' in m_fn:
                            continue
                    kept.append(m)
    except Exception:
        pass
    return kept


def _dh_safe_clear_stray_characters(player=None):
    """Same as clear_stray_characters, but keeps all teammate 3D models in UIMain.models
    and purges stray male creation dummy models."""
    try:
        import BigWorld, Globals
        player = player or BigWorld.player()
        hall = getattr(player, 'hallScene', None)
        if not isinstance(hall, LocalHallScene):
            return 0

        is_female = False
        try:
            c_type = player.getCharacterType() if hasattr(player, 'getCharacterType') else getattr(player, 'characterType', 0)
            data = character_data(c_type) if callable(globals().get('character_data')) else None
            if int(getattr(data, 'GENDER', 1) or 1) == 2 or 'female' in str(getattr(player, 'nickname', '')).lower():
                is_female = True
        except Exception:
            pass

        # Purge stray male creation model from UIMain
        main_ui = getattr(getattr(Globals, 'uiMgr', None), 'UIMain', None)
        models_dict = getattr(main_ui, 'models', None) if main_ui else None
        if isinstance(models_dict, dict):
            for gk, entry in list(models_dict.items()):
                m = entry.get('model') if isinstance(entry, dict) else entry
                if m is not None and m is not hall.__dict__.get('model'):
                    m_fn = str(getattr(m, 'filename', '')).lower()
                    if 'dataosha_male' in m_fn or 'male.gim' in m_fn or 'male_show_new' in m_fn:
                        if is_female or gk not in _team_gids(player):
                            try:
                                m.visible = False
                            except Exception:
                                pass
                            try:
                                destroy_model(m)
                            except Exception:
                                pass
                            models_dict.pop(gk, None)

        keep = ([hall.__dict__.get('model')] +
                [entry[0] for entry in (hall.__dict__.get('_rl_model_cache') or {}).values()] +
                _dh_ui_main_models())
        stray = []
        for model, name in scene_models(hall._native_scene):
            name_lower = str(name).lower()
            if 'dataosha' not in name_lower:
                continue

            # Stray male model standing in center:
            if 'dataosha_male' in name_lower:
                if is_female and model is not hall.__dict__.get('model'):
                    if not any(model is kept for kept in _dh_ui_main_models() if kept is not None):
                        stray.append(model)
                        continue
                elif model is not hall.__dict__.get('model') and at_spot(model, (0.0, 0.0, 0.0), 3.0):
                    if not any(model is kept for kept in _dh_ui_main_models() if kept is not None):
                        stray.append(model)
                        continue

            if any(model is kept for kept in keep if kept is not None):
                continue
            if name_lower.endswith(CHARACTER_MODEL_ENDINGS) or at_spot(model, SELECT_SCREEN_SPOT):
                stray.append(model)

        kept = game_preloaded_models() if callable(globals().get('game_preloaded_models')) else []
        for model in stray:
            try:
                model.visible = False
            except Exception:
                pass
            if not any(model is other for other in kept):
                try:
                    destroy_model(model)
                except Exception:
                    pass
        if stray:
            log('local-lobby-stray-characters-cleared', count=len(stray))
        return len(stray)
    except Exception:
        log_error('local-lobby-safe-stray-clear-error')
        return 0


globals()['clear_stray_characters'] = _dh_safe_clear_stray_characters'''

    new_block_2 = '''def _dh_party_main_ready(*args, **kwargs):
    try:
        import BigWorld
        BigWorld._dh_theme_suspended = False
        p = BigWorld.player()
        own = _dh_theme_own()
        target_th = own if own else 279008
        if p is not None:
            cur_th = getattr(p, 'dtsHallThemeID', 0) or 0
            if not cur_th or cur_th == 270000:
                p.dtsHallThemeID = target_th

        # Unhide all sky and backdrop models when UIMain becomes ready
        hall = getattr(p, 'hallScene', None) if p else None
        scene = getattr(hall, '_native_scene', None) if hall else None
        if scene is not None:
            for model, name in scene_models(scene):
                name_lower = str(name).lower()
                if any(k in name_lower for k in ('plane_bg', 'sky', 'mountain', 'road', 'city', 'building', 'terrain')):
                    if 'motor' not in name_lower:
                        try:
                            model.visible = True
                        except Exception:
                            pass
        _lobby['retired_hall_models'] = []
        _lobby['native_hall_models'] = []
        _lobby['backdrop_hidden'] = False

        # Clear select character preloaded model so it cannot leak
        try:
            import ui.UISelectCharacter as select_module
            select_module._rl_preloaded_model = None
        except Exception:
            pass

        # Also purge any stray characters right now
        _dh_safe_clear_stray_characters(p)
    except Exception:
        pass
    res = _dh_orig_main_ready(*args, **kwargs) if callable(_dh_orig_main_ready) else None
    try:
        import BigWorld
        player = BigWorld.player()
        if player is not None:
            call_later(0.2, _dh_apply_party_enter_when_ready, 0)
            call_later(0.5, ask_party_state, player)
            call_later(2.0, ask_party_state, player)
    except Exception:
        pass
    return res


_dh_party_main_ready._dh_party_ready_inner = _dh_orig_main_ready
globals()['_dh_main_ready'] = _dh_party_main_ready



# Guard start_local_lobby against lingering ClientTeammate entities from battle quit
_dh_orig_start_local_lobby = globals().get('start_local_lobby')
while getattr(_dh_orig_start_local_lobby, '_dh_guard_inner', None) is not None:
    _dh_orig_start_local_lobby = _dh_orig_start_local_lobby._dh_guard_inner


def _dh_guarded_start_local_lobby(*args, **kwargs):
    retry_count = kwargs.pop('_dh_retry', 0)
    try:
        import BigWorld
        p = BigWorld.player()
        if p is None or not hasattr(p, 'onBecomePlayer'):
            if retry_count < 60:
                kwargs['_dh_retry'] = retry_count + 1
                call_later(0.2, _dh_guarded_start_local_lobby, *args, **kwargs)
                return None
        p_cname = getattr(getattr(p, '__class__', None), '__name__', '')
        if p_cname == 'ClientTeammate' or 'ClientTeammate' in str(type(p)):
            for ent in list(BigWorld.entities.values()):
                if ent is not None and getattr(getattr(ent, '__class__', None), '__name__', '') == 'ClientTeammate':
                    try:
                        BigWorld.destroyEntity(ent.id)
                    except Exception:
                        pass
    except Exception:
        pass
    try:
        # Reset backdrop retirement on return to lobby
        _lobby['retired_hall_models'] = []
        _lobby['native_hall_models'] = []
        _lobby['backdrop_hidden'] = False
        import ui.UISelectCharacter as select_module
        select_module._rl_preloaded_model = None
    except Exception:
        pass
    if callable(_dh_orig_start_local_lobby):
        res = _dh_orig_start_local_lobby(*args, **kwargs)
        try:
            call_later(0.5, _dh_kick_stuck_lobby)
        except Exception:
            pass
        return res
    return None


if callable(_dh_orig_start_local_lobby):
    _dh_guarded_start_local_lobby._dh_guard_inner = _dh_orig_start_local_lobby
    globals()['start_local_lobby'] = _dh_guarded_start_local_lobby'''

    if '_dh_safe_ensure_self_model' in content:
        print('Block 1 already applied!')
    else:
        m1_start = '    # Clean native backdrop passthroughs: respects the game\'s hiding of backdrops'
        m1_end = 'globals()[\'clear_stray_characters\'] = _dh_safe_clear_stray_characters'
        p1 = content.find(m1_start)
        p2 = content.find(m1_end) + len(m1_end) if content.find(m1_end) != -1 else -1

        if p1 != -1 and p2 != -1:
            content = content[:p1] + new_block_1 + content[p2:]
            print('Block 1 replaced successfully')
        else:
            print('Error: Block 1 markers not found!', p1, p2)

    if "_lobby['native_hall_models'] = []" in content and '_dh_safe_clear_stray_characters(p)' in content:
        print('Block 2 already applied!')
    else:
        m2_start = 'def _dh_party_main_ready(*args, **kwargs):'
        m2_end = 'globals()[\'start_local_lobby\'] = _dh_guarded_start_local_lobby'
        p3 = content.find(m2_start)
        p4 = content.find(m2_end) + len(m2_end) if content.find(m2_end) != -1 else -1

        if p3 != -1 and p4 != -1:
            content = content[:p3] + new_block_2 + content[p4:]
            print('Block 2 replaced successfully')
        else:
            print('Error: Block 2 markers not found!', p3, p4)

    with open('clean_remote_lobby.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('clean_remote_lobby.py saved!')

if __name__ == '__main__':
    run_patch()
