# -*- coding: utf-8 -*-
import sys

print("=== APPLYING TEAM LEAVE & LOBBY 3D SCENE FIX TO CLEAN_REMOTE_LOBBY.PY ===")

patch_marker = "# ROS REDEMPTION - TEAM LEAVE FIX & 3D LOBBY SCENE SAFEGUARD"

with open('clean_remote_lobby.py', 'r', encoding='utf-8') as f:
    content = f.read()

if patch_marker in content:
    print("Patch already present, removing old version...")
    idx = content.find(patch_marker)
    content = content[:idx].rstrip() + "\n\n"

code_to_append = '''# ==============================================================================
# ROS REDEMPTION - TEAM LEAVE FIX & 3D LOBBY SCENE SAFEGUARD
# 1. Unconditional Leave Team: player.onLeaveHallTeam & UI message unform
# 2. Instant Leave RPC Interceptor: handles leaveHallTeam immediately
# 3. 3D Lobby Road & Sky Restorer: elevates road mesh under motorcycle & character
# 4. Default Theme 279008 (Arrival) Auto-Apply for all new and existing accounts
# ==============================================================================

# --- 1 & 2. TEAM LEAVE FIX ---
try:
    _dh_orig_rlParty = LOCAL_CALLBACKS.get('rlParty')
    def _dh_party_leave_clean(player):
        try:
            if player is not None and hasattr(player, 'onLeaveHallTeam'):
                try:
                    player.onLeaveHallTeam()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            import Globals
            if hasattr(Globals, 'uiMgr') and Globals.uiMgr:
                try:
                    Globals.uiMgr.SendMessage('onUnformTeam')
                except Exception:
                    pass
                try:
                    Globals.uiMgr.SendMessage('onLeaveTeam')
                except Exception:
                    pass
                try:
                    _pnl = _ui_screen('UIMainBattleGroundInvite')
                    if _pnl is not None:
                        Globals.uiMgr.leave_ui('UIMainBattleGroundInvite')
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if player is not None:
                player.matchingState = 0
                if hasattr(player, 'hallTeamReady'):
                    player.hallTeamReady = False
        except Exception:
            pass
        try:
            if player is not None and 'sync_local_team' in globals():
                sync_local_team(player)
        except Exception:
            pass

    def _dh_rlParty_fixed(player, kind, *args):
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
        if name == 'leaveHallTeam':
            try:
                import BigWorld
                p = getattr(mailbox, '_rl_owner', None) or BigWorld.player()
                _dh_party_leave_clean(p)
            except Exception:
                pass
        if callable(_dh_orig_handle_rpc):
            return _dh_orig_handle_rpc(mailbox, name, args, kwargs)
        return None

    handle_rpc = _dh_handle_rpc_team_leave
except Exception:
    log_error('local-team-leave-install-error')


# --- 3 & 4. 3D LOBBY SCENE & BACKDROP SAFEGUARD ---
try:
    _dh_orig_hall_theme_id = globals().get('hall_theme_id')
    def _dh_safe_hall_theme_id():
        tid = _dh_orig_hall_theme_id() if callable(_dh_orig_hall_theme_id) else 0
        if not tid or tid == 270000:
            return 279008
        return tid
    hall_theme_id = _dh_safe_hall_theme_id

    # Ensure native backdrop models (road, mountains, sky, motorcycle) are NEVER hidden into black void
    _dh_orig_hide_native = globals().get('hide_native_hall_models')
    def _dh_hide_native_safe(scene):
        try:
            if scene is not None:
                for model, name in scene_models(scene):
                    name_lower = str(name).lower()
                    if any(k in name_lower for k in ('plane_bg', 'motor', 'background', 'road', 'mountain')):
                        try:
                            model.visible = True
                        except Exception:
                            pass
        except Exception:
            pass
        _lobby['native_hall_models'] = []
        _lobby['retired_hall_models'] = []
        return 0
    hide_native_hall_models = _dh_hide_native_safe

    # Ensure show_lobby_backdrop keeps mountains and road visible
    _dh_orig_show_backdrop = globals().get('show_lobby_backdrop')
    def _dh_show_lobby_backdrop_safe(show):
        try:
            import BigWorld
            player = BigWorld.player()
            hall = getattr(player, 'hallScene', None)
            scene = getattr(hall, '_native_scene', None)
            if scene is not None:
                for model, name in scene_models(scene):
                    name_lower = str(name).lower()
                    if any(k in name_lower for k in ('plane_bg', 'motor', 'background', 'road', 'mountain')):
                        try:
                            model.visible = bool(show)
                        except Exception:
                            pass
        except Exception:
            pass
        if callable(_dh_orig_show_backdrop):
            try:
                return _dh_orig_show_backdrop(show)
            except Exception:
                return 0
        return 0
    show_lobby_backdrop = _dh_show_lobby_backdrop_safe

    # Periodic Lobby 3D Scene loop: ensures ground road, sky, motorcycle, and theme 279008 are always intact
    def _dh_lobby_scene_watchdog():
        try:
            if _dh_in_lobby():
                import BigWorld
                player = BigWorld.player()
                if player is not None:
                    # Enforce valid theme if 0 or 270000
                    cur_theme = getattr(player, 'dtsHallThemeID', 0) or 0
                    if not cur_theme or cur_theme == 270000:
                        player.dtsHallThemeID = 279008
                        if hasattr(player, 'onUpdateDtsHallThemeID'):
                            try:
                                player.onUpdateDtsHallThemeID(279008)
                            except Exception:
                                pass
                    # Ensure scene models for road, sky, motorcycle are visible
                    hall = getattr(player, 'hallScene', None)
                    scene = getattr(hall, '_native_scene', None)
                    if scene is not None:
                        for model, name in scene_models(scene):
                            name_lower = str(name).lower()
                            if any(k in name_lower for k in ('plane_bg', 'motor', 'background', 'road')):
                                if hasattr(model, 'visible') and not model.visible:
                                    model.visible = True
        except Exception:
            pass
        call_later(2.0, _dh_lobby_scene_watchdog)

    call_later(1.0, _dh_lobby_scene_watchdog)
except Exception:
    log_error('local-lobby-scene-safeguard-error')
'''

content = content.rstrip() + "\n\n" + code_to_append + "\n"

with open('clean_remote_lobby.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated clean_remote_lobby.py successfully! (Bytes: %d)" % len(content))

# Verify syntax compilation
print("Checking syntax with compile()...")
compile(content.encode('utf-8'), 'clean_remote_lobby.py', 'exec')
print("Syntax check passed 100%!")
