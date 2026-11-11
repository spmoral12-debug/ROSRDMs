# -*- coding: utf-8 -*-
import os, sys

def patch_file(filepath):
    print("Patching %s..." % filepath)
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # 1. Un-nest mall_buy_details
    target_mall_1 = "_dh_orig_mall_buy_details = globals().get('mall_buy_details')"
    repl_mall_1 = """_dh_orig_mall_buy_details = globals().get('mall_buy_details')
while getattr(_dh_orig_mall_buy_details, '_dh_pack_buy_inner', None) is not None:
    _dh_orig_mall_buy_details = _dh_orig_mall_buy_details._dh_pack_buy_inner"""

    if target_mall_1 in content and '_dh_pack_buy_inner' not in content:
        content = content.replace(target_mall_1, repl_mall_1, 1)
        content = content.replace(
            "mall_buy_details = _dh_mall_buy_details_with_pack_state",
            "_dh_mall_buy_details_with_pack_state._dh_pack_buy_inner = _dh_orig_mall_buy_details\nmall_buy_details = _dh_mall_buy_details_with_pack_state\nglobals()['mall_buy_details'] = _dh_mall_buy_details_with_pack_state",
            1
        )
        print("  - Fixed mall_buy_details wrapping")

    # 2. Un-nest _dh_orig_rlParty and _dh_orig_handle_rpc
    old_team_block = """    def _dh_rlParty_fixed(player, kind, *args):
        kind_str = str(kind)
        if kind_str == 'left':
            log('local-team-leave-handled', kind=kind_str)
            _dh_party_leave_clean(player)
            return None
        if callable(_dh_orig_rlParty):
            return _dh_orig_rlParty(player, kind, *args)
        return None

    LOCAL_CALLBACKS['rlParty'] = _dh_rlParty_fixed

    # Wrap handle_rpc for immediate leave response when player clicks Leave button
    _dh_orig_handle_rpc = globals().get('handle_rpc')
    def _dh_handle_rpc_team_leave(mailbox, name, args, kwargs):
        if name in ('leaveHallTeam', 'unformHallTeam', 'dismissHallTeam', 'leaveTeam'):
            try:
                import BigWorld
                p = getattr(mailbox, '_rl_owner', None) or BigWorld.player()
                _dh_party_leave_clean(p)
            except Exception:
                pass
        if callable(_dh_orig_handle_rpc):
            return _dh_orig_handle_rpc(mailbox, name, args, kwargs)
        return None

    handle_rpc = _dh_handle_rpc_team_leave"""

    new_team_block = """    _dh_orig_rlParty = LOCAL_CALLBACKS.get('rlParty')
    while getattr(_dh_orig_rlParty, '_dh_party_fixed_inner', None) is not None:
        _dh_orig_rlParty = _dh_orig_rlParty._dh_party_fixed_inner
    def _dh_rlParty_fixed(player, kind, *args):
        kind_str = str(kind)
        if kind_str == 'left':
            log('local-team-leave-handled', kind=kind_str)
            _dh_party_leave_clean(player)
            return None
        if callable(_dh_orig_rlParty):
            return _dh_orig_rlParty(player, kind, *args)
        return None
    _dh_rlParty_fixed._dh_party_fixed_inner = _dh_orig_rlParty
    LOCAL_CALLBACKS['rlParty'] = _dh_rlParty_fixed

    # Wrap handle_rpc for immediate leave response when player clicks Leave button
    _dh_orig_handle_rpc = globals().get('handle_rpc')
    while getattr(_dh_orig_handle_rpc, '_dh_team_leave_inner', None) is not None:
        _dh_orig_handle_rpc = _dh_orig_handle_rpc._dh_team_leave_inner
    def _dh_handle_rpc_team_leave(mailbox, name, args, kwargs):
        if name in ('leaveHallTeam', 'unformHallTeam', 'dismissHallTeam', 'leaveTeam'):
            try:
                import BigWorld
                p = getattr(mailbox, '_rl_owner', None) or BigWorld.player()
                _dh_party_leave_clean(p)
            except Exception:
                pass
        if callable(_dh_orig_handle_rpc):
            return _dh_orig_handle_rpc(mailbox, name, args, kwargs)
        return None
    _dh_handle_rpc_team_leave._dh_team_leave_inner = _dh_orig_handle_rpc
    handle_rpc = _dh_handle_rpc_team_leave
    globals()['handle_rpc'] = _dh_handle_rpc_team_leave"""

    if old_team_block in content:
        content = content.replace(old_team_block, new_team_block, 1)
        print("  - Fixed _dh_handle_rpc_team_leave and _dh_rlParty_fixed unwrap")

    # 3. Un-nest hall_theme_id
    old_theme_id_block = """    _dh_orig_hall_theme_id = globals().get('hall_theme_id')
    def _dh_safe_hall_theme_id():
        own = _dh_theme_own()
        if own:
            return own
        tid = _dh_orig_hall_theme_id() if callable(_dh_orig_hall_theme_id) else 0
        if not tid or tid == 270000:
            return 279008
        return tid
    hall_theme_id = _dh_safe_hall_theme_id
    globals()['hall_theme_id'] = _dh_safe_hall_theme_id"""

    new_theme_id_block = """    _dh_orig_hall_theme_id = globals().get('hall_theme_id')
    while getattr(_dh_orig_hall_theme_id, '_dh_theme_inner', None) is not None:
        _dh_orig_hall_theme_id = _dh_orig_hall_theme_id._dh_theme_inner
    def _dh_safe_hall_theme_id():
        own = _dh_theme_own()
        if own:
            return own
        tid = _dh_orig_hall_theme_id() if callable(_dh_orig_hall_theme_id) else 0
        if not tid or tid == 270000:
            return 279008
        return tid
    _dh_safe_hall_theme_id._dh_theme_inner = _dh_orig_hall_theme_id
    hall_theme_id = _dh_safe_hall_theme_id
    globals()['hall_theme_id'] = _dh_safe_hall_theme_id"""

    if old_theme_id_block in content:
        content = content.replace(old_theme_id_block, new_theme_id_block, 1)
        print("  - Fixed hall_theme_id unwrap")

    # 4. Un-nest ensure_self_model
    old_ensure_block = """    _dh_orig_ensure_self_model = globals().get('ensure_self_model')
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
    globals()['ensure_self_model'] = _dh_safe_ensure_self_model"""

    new_ensure_block = """    _dh_orig_ensure_self_model = globals().get('ensure_self_model')
    while getattr(_dh_orig_ensure_self_model, '_dh_ensure_inner', None) is not None:
        _dh_orig_ensure_self_model = _dh_orig_ensure_self_model._dh_ensure_inner
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
    _dh_safe_ensure_self_model._dh_ensure_inner = _dh_orig_ensure_self_model
    ensure_self_model = _dh_safe_ensure_self_model
    globals()['ensure_self_model'] = _dh_safe_ensure_self_model"""

    if old_ensure_block in content:
        content = content.replace(old_ensure_block, new_ensure_block, 1)
        print("  - Fixed ensure_self_model unwrap")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("  => Saved %s" % filepath)

if __name__ == '__main__':
    targets = [
        'clean_remote_lobby.py',
        r'c:\Users\LEGION 7 RTX 3080\Downloads\ROSRDMs-collab\clean_remote_lobby.py'
    ]
    for t in targets:
        if os.path.exists(t):
            patch_file(t)
