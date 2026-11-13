# Appended to the local client hook (embedded Python 2.7).
def _redemption_profile_metadata(player):
    try:
        lobby = load_state().get('lobby', {})
        flag = lobby.get('nationalFlag') or lobby.get('country') or lobby.get('nation') or lobby.get('flag')
        if flag:
            flag_str = to_native_str(flag)
            player.nationalFlag = flag_str
            record = {'flag': flag_str}
            if lobby.get('nationalFlagSetTime'):
                record['setTime'] = lobby['nationalFlagSetTime']
            try:
                player.updateNationalityInfo([record])
            except Exception:
                pass
        # Make calcSetNationFlagYB always return 0 (free) so country flag selection never prompts for diamonds
        try:
            player.calcSetNationFlagYB = lambda *args, **kwargs: 0
        except Exception:
            pass
        # Make getExtraCommonInfo return False for freeNickNameUsed so nickname rename is always free
        try:
            _orig_extra = getattr(player, 'getExtraCommonInfo', None)
            if _orig_extra is not None and not getattr(_orig_extra, '_dh_free', False):
                def _free_extra(infoKey, defaultValue=None):
                    if infoKey == 'freeNickNameUsed':
                        return False
                    return _orig_extra(infoKey, defaultValue)
                _free_extra._dh_free = True
                player.getExtraCommonInfo = _free_extra
        except Exception:
            pass
    except Exception:
        pass


def _redemption_nickname_changed(player, name):
    try:
        import gc
        import Globals
        name = to_native_str(name)
        state = load_state()
        state.setdefault('player', {})['nickname'] = name
        state.setdefault('lobby', {})['freeNickNameUsed'] = False
        local_player.nickname = name
        for prop in ('baseNickname', 'nickname', 'playerName'):
            try:
                setattr(player, prop, name)
            except Exception:
                pass
        _redemption_profile_metadata(player)
        try:
            Globals.uiMgr.leave_ui('UIChangeNickname')
        except Exception:
            pass
        try:
            refresh_lobby_profile()
        except Exception:
            pass
        # The nameplate reads the lobby team slot, which has its own name fields.
        try:
            member = (getattr(player, 'hallTeamData', None) or {}).get(player.gid)
            if member is not None:
                member['nickname'] = name
                member['baseNickname'] = name
                main_ui = getattr(Globals.uiMgr, 'UIMain', None)
                if main_ui is not None:
                    main_ui.onFormTeam(False)
        except Exception:
            log_error('local-redemption-nameplate-refresh-error')
        for panel in gc.get_objects():
            if type(panel).__name__ == 'UIBattleGroundRecordPanel':
                try:
                    panel.updateNickname(player.gid, name)
                except Exception:
                    pass
    except Exception:
        pass


def _redemption_flag_changed(player, code, changed_at=None):
    try:
        import Globals
        flag_str = to_native_str(code)
        lobby = load_state().setdefault('lobby', {})
        lobby['nationalFlag'] = flag_str
        lobby['country'] = flag_str
        lobby['flag'] = flag_str
        lobby['nation'] = flag_str
        if changed_at:
            lobby['nationalFlagSetTime'] = changed_at
        
        player.nationalFlag = flag_str
        record = {'flag': flag_str}
        if changed_at:
            record['setTime'] = changed_at
        try:
            player.updateNationalityInfo([record])
        except Exception:
            pass
        try:
            Globals.uiMgr.leave_ui('UINationalitySelect')
        except Exception:
            pass
        try:
            refresh_lobby_profile()
        except Exception:
            pass
    except Exception:
        pass


def _local_on_change_nickname(player, ret, msg=''):
    try:
        import Globals
        if ret == 0:
            try:
                Globals.uiMgr.leave_ui('UIChangeNickname')
            except Exception:
                pass
            try:
                refresh_lobby_profile()
            except Exception:
                pass
        elif msg:
            Globals.uiMgr.systemJumpTip(to_native_str(msg))
    except Exception:
        pass


LOCAL_CALLBACKS['rlRedemptionNickname'] = _redemption_nickname_changed
LOCAL_CALLBACKS['rlRedemptionFlag'] = _redemption_flag_changed
LOCAL_CALLBACKS['onChangeNickname'] = _local_on_change_nickname

# Hook apply_local_profile so profile metadata & flag are always set on entry
try:
    _orig_apply_local_profile = apply_local_profile
    def apply_local_profile(player):
        res = _orig_apply_local_profile(player)
        try:
            _redemption_profile_metadata(player)
        except Exception:
            pass
        return res
except Exception:
    pass

# Ensure country flag is active on lobby startup
try:
    def _dh_ensure_flag_tick():
        try:
            import BigWorld
            p = BigWorld.player()
            if p is not None:
                _redemption_profile_metadata(p)
        except Exception:
            pass
        call_later(2.0, _dh_ensure_flag_tick)
    call_later(2.0, _dh_ensure_flag_tick)
except Exception:
    pass
