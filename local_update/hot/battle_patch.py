# ==========================================================
# ROS REDEMPTION - BATTLE HOT PATCH
# ==========================================================
# 1. UISelectHero exception guard & non-hero map suppression
# 2. Fast matchmaking (max 1.5s wait before countdown)
# 3. Resilient step_join (drains queue, retries, graceful fallback)
# 4. iTrainSpace & iPerspective guards
# ==========================================================
import sys
import time
import json
import math

def _patch_train_space():
    try:
        mod = sys.modules.get('iTrainSpace')
        if not mod:
            try:
                import iTrainSpace as mod
            except Exception:
                mod = None
        if mod and hasattr(mod, 'iTrainSpace'):
            cls = mod.iTrainSpace
            orig = getattr(cls, 'refreshMapUI', None)
            if orig and not getattr(orig, '_redemption_guard', False):
                def safe_refreshMapUI(self, *args, **kwargs):
                    try:
                        return orig(self, *args, **kwargs)
                    except Exception:
                        return None
                safe_refreshMapUI._redemption_guard = True
                cls.refreshMapUI = safe_refreshMapUI
                log('ros-redemption-patch', fix='iTrainSpace.refreshMapUI guarded')
    except Exception:
        pass

def _patch_perspective():
    try:
        mod = sys.modules.get('iPerspective')
        if not mod:
            try:
                import iPerspective as mod
            except Exception:
                mod = None
        if mod and hasattr(mod, 'iPerspective'):
            cls = mod.iPerspective
            orig = getattr(cls, 'isPerspected', None)
            if orig and not getattr(orig, '_redemption_guard', False):
                def safe_isPerspected(self, *args, **kwargs):
                    try:
                        return orig(self, *args, **kwargs)
                    except Exception:
                        return False
                safe_isPerspected._redemption_guard = True
                cls.isPerspected = safe_isPerspected
                log('ros-redemption-patch', fix='iPerspective.isPerspected guarded')
    except Exception:
        pass

def _patch_ui_select_hero():
    try:
        # 1. Guard UISelectHero._showHeroList
        for mod_name in ('ui.UISelectHero', 'UISelectHero'):
            mod = sys.modules.get(mod_name)
            if not mod:
                try:
                    mod = __import__(mod_name, fromlist=['UISelectHero'])
                except Exception:
                    mod = None
            if mod:
                cls = getattr(mod, 'UISelectHero', None)
                if cls:
                    orig = getattr(cls, '_showHeroList', None)
                    if orig and not getattr(orig, '_redemption_guard', False):
                        def safe_showHeroList(self, *args, **kwargs):
                            try:
                                return orig(self, *args, **kwargs)
                            except Exception:
                                return None
                        safe_showHeroList._redemption_guard = True
                        cls._showHeroList = safe_showHeroList
                        log('ros-redemption-patch', fix='UISelectHero._showHeroList guarded')

        # 2. Guard Globals.uiMgr.enter_ui for non-hero maps
        import Globals
        if hasattr(Globals, 'uiMgr'):
            orig_enter = getattr(Globals.uiMgr, 'enter_ui', None)
            if orig_enter and not getattr(orig_enter, '_redemption_guard', False):
                def safe_enter_ui(name, *args, **kwargs):
                    if name == 'UISelectHero':
                        cur_map = BATTLE.get('map') or (BATTLE.get('ticket') or {}).get('map', 0)
                        if cur_map not in (730, 731, 732, 733):
                            return None
                    return orig_enter(name, *args, **kwargs)
                safe_enter_ui._redemption_guard = True
                Globals.uiMgr.enter_ui = safe_enter_ui
                log('ros-redemption-patch', fix='Globals.uiMgr.enter_ui UISelectHero filtered')
    except Exception:
        pass

def _patch_matching():
    try:
        if 'BATTLE' in globals() and 'match_found' in globals():
            def redemption_matching_tick(player):
                if BATTLE.get('phase') != 'matching':
                    return
                for packet in drain():
                    if isinstance(packet, dict) and 'queued' in packet:
                        BATTLE['queue'] = packet
                queue = BATTLE.get('queue')
                elapsed = time.time() - BATTLE.get('matching_started', 0.0)

                # Fast match start
                if (queue is not None and queue.get('go')) or elapsed >= 1.5:
                    log('local-battle-queue-go', queued=(queue or {}).get('queued', 1),
                        need=(queue or {}).get('need', 1), elapsed=elapsed)
                    match_found(player)
                    return

                _call(player, 'syncMatchingProgress', 1, 1, 0)
                session = LOBBY._backend.get('session') if LOBBY is not None and hasattr(LOBBY, '_backend') else ''
                send(QUEUE_PREFIX + json.dumps({'session': session or 'sean_solo'}))
                call_later(0.3, redemption_matching_tick, player)

            globals()['matching_tick'] = redemption_matching_tick
            log('ros-redemption-patch', fix='fast matchmaking installed')
    except Exception:
        pass

def _patch_step_join():
    try:
        if 'ENTER_STEPS' in globals() and 'BATTLE' in globals():
            def redemption_step_join(player):
                session = LOBBY._backend.get('session') if LOBBY is not None and hasattr(LOBBY, '_backend') else ''
                if not session:
                    session = 'sean_redemption_session'
                profile = {}
                try:
                    profile = LOBBY._local_profile(player)
                except Exception:
                    pass
                map_id, source = wanted_map(player)
                spawn = configured_spawn(map_id)
                spawn_from = 'configured' if spawn is not None else 'map'
                if spawn is None:
                    spawn = map_birth_point(map_id)
                if spawn is None:
                    spawn = map_born_point(map_id)
                if spawn is None:
                    centre = map_play_centre(map_id)
                    if centre is not None:
                        spawn = (centre[0], PROVISIONAL_HEIGHT, centre[1])
                if spawn is None:
                    height = _point((BATTLE['ticket'] or {}).get('spawn') or (0.0, 100.0, 0.0))[1] or 100.0
                    spawn = map_spawn(map_id, height)
                randomized = False
                if spawn_from == 'configured':
                    picked = island_reborn_point(map_id)
                    if picked is not None:
                        spawn, randomized = picked, True
                BATTLE.update(map=map_id, map_from=source, spawn=spawn, spawn_from=spawn_from, spawn_randomized=randomized)
                request = {
                    'session': session,
                    'name': str(profile.get('nickname') or 'sean'),
                    'gid': int(profile.get('gid') or 10000001),
                    'map': map_id,
                    'look': my_look(player),
                    'team': int((BATTLE['ticket'] or {}).get('team') or 1),
                }
                if spawn is not None:
                    request['spawn'] = [round(value, 3) for value in spawn]

                # Clear old packets
                drain(32)

                reply = ask(JOIN_PREFIX + json.dumps(request), timeout=4.0, accept=is_join_reply, resend_every=0.5)
                if not isinstance(reply, dict) or not reply.get('ok'):
                    log('local-battle-join-fallback', req=request)
                    reply = {
                        'ok': True,
                        'you': {'id': 41, 'kind': 'player', 'name': request['name'], 'team': request['team']},
                        'match': {'battle': 1, 'map': map_id, 'bots': 40}
                    }

                you = reply.get('you') or {}
                BATTLE['entity_id'] = int(you.get('id') or 41)
                BATTLE['match'] = reply.get('match') or {'battle': 1, 'map': map_id, 'bots': 40}
                log('local-battle-joined', entity=BATTLE['entity_id'], map=BATTLE['map'],
                    map_from=BATTLE['map_from'], bots=BATTLE['match'].get('bots', 40),
                    spawn=list(_spawn_point()),
                    spawn_from='map' if BATTLE['spawn'] is not None else 'battle-host')
                return 'ok'

            new_steps = []
            for name, func in ENTER_STEPS:
                if name == 'join':
                    new_steps.append((name, redemption_step_join))
                else:
                    new_steps.append((name, func))
            globals()['ENTER_STEPS'] = tuple(new_steps)
            globals()['step_join'] = redemption_step_join
            log('ros-redemption-patch', fix='resilient step_join installed')
    except Exception:
        pass

try:
    _patch_train_space()
    _patch_perspective()
    _patch_ui_select_hero()
    _patch_matching()
    _patch_step_join()
    log('ros-redemption-battle-patch-loaded', status='active')
except Exception:
    pass
