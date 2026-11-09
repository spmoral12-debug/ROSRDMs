# Appended to the local client hook (embedded Python 2.7).
def _redemption_profile_metadata(player):
    lobby = load_state().get('lobby', {})
    if lobby.get('freeNickNameUsed'):
        extra = getattr(player, 'extraCommonInfo', None)
        if extra is None or not hasattr(extra, 'get'):
            extra = {}
        extra['freeNickNameUsed'] = True
        player.extraCommonInfo = extra
    flag = lobby.get('nationalFlag')
    if flag:
        player.nationalFlag = to_native_str(flag)
        record = {'flag': player.nationalFlag}
        if lobby.get('nationalFlagSetTime'):
            record['setTime'] = lobby['nationalFlagSetTime']
        player.updateNationalityInfo([record])


def _redemption_nickname_changed(player, name):
    import gc
    import Globals
    name = to_native_str(name)
    state = load_state()
    state.setdefault('player', {})['nickname'] = name
    state.setdefault('lobby', {})['freeNickNameUsed'] = True
    local_player.nickname = name
    for prop in ('baseNickname', 'nickname', 'playerName'):
        setattr(player, prop, name)
    _redemption_profile_metadata(player)
    Globals.uiMgr.leave_ui('UIChangeNickname')
    refresh_lobby_profile()
    for panel in gc.get_objects():
        if type(panel).__name__ == 'UIBattleGroundRecordPanel':
            try:
                panel.updateNickname(player.gid, name)
            except Exception:
                pass


def _redemption_flag_changed(player, code, changed_at):
    lobby = load_state().setdefault('lobby', {})
    lobby['nationalFlag'] = to_native_str(code)
    lobby['nationalFlagSetTime'] = changed_at
    _redemption_profile_metadata(player)
    refresh_lobby_profile()


_redemption_apply_profile = apply_local_profile


def apply_local_profile(player):
    result = _redemption_apply_profile(player)
    try:
        _redemption_profile_metadata(player)
    except Exception:
        log_error('local-redemption-profile-metadata-error')
    return result


LOCAL_CALLBACKS['rlRedemptionNickname'] = _redemption_nickname_changed
LOCAL_CALLBACKS['rlRedemptionFlag'] = _redemption_flag_changed
