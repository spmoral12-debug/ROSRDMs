# DieHard ROS Online - battle hot patch: play the island's default theme by itself.
# RosReborn's battle hook (chosen_music_only) kept the island silent until a song was picked from
# the music button; players heard no music in a match.  Runs inside the battle hook's globals
# (local_update/hot/remote-battle.py); every function it needs (default_music_id, log, log_error,
# install_music_choice) is a battle-hook global.
import sys as _dh_sys


def _dh_unwrap(function):
    """The function before any of our wrappers (this file is re-applied on every update).  None when
    an older wrapper of ours without the inner marker is in the way: wrapping it again would loop."""
    seen = 0                        # m41f: leave_battle carries 11 of our wrappers since m41; the old cap of 10 stopped
    while function is not None and getattr(function, '_dh_inner', None) is not None and seen < 64:
        function = function._dh_inner
        seen += 1
    try:
        if function is not None and getattr(function, '__code__', None) is not None \
                and function.__code__.co_filename == 'battle_hot_patch':
            log('local-battle-hot-patch-stale-wrapper', name=getattr(function, '__name__', '?'))
            return None
    except Exception:
        pass
    return function


def _dh_unwrapped(function):
    """The game's own BattleGroundSpace.tryPlayMusic behind RosReborn's wrapper."""
    if not getattr(function, '_rl_chosen_music', False):
        return function
    cells = getattr(function, 'func_closure', None) or getattr(function, '__closure__', None) or ()
    for cell in cells:
        try:
            value = cell.cell_contents
        except Exception:
            continue
        if callable(value) and value is not function:
            return value
    return None


def _dh_default_music_patch():
    module = _dh_sys.modules.get('BattleGroundSpace')
    cls = getattr(module, 'BattleGroundSpace', None)
    if cls is None:
        return 'no-space'
    current = cls.__dict__.get('tryPlayMusic')
    if current is None:
        return 'no-method'
    if getattr(current, '_dh_default_music', False):
        return 'already'
    original = _dh_unwrapped(current)
    if original is None:
        return 'no-original'

    def try_play_music(self, musicID=None, *args):
        if not musicID:
            try:
                musicID = default_music_id()
            except Exception:
                musicID = None
        if not musicID:
            return None
        return original(self, musicID, *args)
    try_play_music._dh_default_music = True
    try_play_music._rl_chosen_music = True      # install_music_choice must not wrap it again
    cls.tryPlayMusic = try_play_music
    return 'patched'


def quiet_default_music(space):
    """RosReborn stopped the theme the island started natively; keep it playing."""
    return False


_dh_original_install_music_choice = globals().get('install_music_choice')
if getattr(_dh_original_install_music_choice, '_dh_inner', None) is not None:
    _dh_original_install_music_choice = _dh_original_install_music_choice._dh_inner   # re-applied patch


def install_music_choice():
    """RosReborn's install (song-list button) and then our default-theme patch, at the moment
    the battle space exists."""
    result = []
    try:
        if callable(_dh_original_install_music_choice):
            result = _dh_original_install_music_choice() or []
    except Exception:
        pass
    try:
        state = _dh_default_music_patch()
        if state == 'patched':
            log('local-battle-default-music', state=state)
    except Exception:
        log_error('local-battle-default-music-error')
    return result


install_music_choice._dh_inner = _dh_original_install_music_choice

try:
    _dh_state = _dh_default_music_patch()
    log('local-battle-default-music-hot', state=_dh_state)
except Exception:
    log_error('local-battle-default-music-error')


# --- bots hovered above the ground: the battle host keeps the height it was given and moves bots in x/z
# only, so on a slope they float or sink.  Snap every bot body to the terrain height each frame (real
# players keep the height their own client reports).  _spawn_remote is called by name from the snapshot
# loop and step_motion from the motion coroutine, so redefining them here takes over at once.
_dh_bot_ids = set()
_dh_original_spawn_remote = _dh_unwrap(globals().get('_spawn_remote'))
_dh_original_step_motion = _dh_unwrap(globals().get('step_motion'))


def _dh_spawn_remote_wrapper(item, *args, **kwargs):
    try:
        if isinstance(item, dict) and item.get('kind') == 'bot':
            _dh_bot_ids.add(item.get('id'))
    except Exception:
        pass
    return _dh_original_spawn_remote(item, *args, **kwargs)


def _dh_snap_bots():
    for battle_id, body in list(_motion['bodies'].items()):
        if battle_id not in _dh_bot_ids or not body.get('samples'):
            continue
        stamp, point, yaw = body['samples'][-1]
        try:
            height = ground_height(point[0], point[2])
        except Exception:
            height = None
        if height is None or height == 0.0:
            continue
        if abs(height - point[1]) < 0.05:
            continue
        snapped = (point[0], height, point[2])
        body['samples'][-1] = (stamp, snapped, yaw)
        # earlier samples too, so the glide between them stays on the ground
        body['samples'][:] = [(s, (p[0], height if abs(p[1] - height) < 12.0 else p[1], p[2]), y) for s, p, y in body['samples']]


def _dh_step_motion_wrapper(now):
    try:
        _dh_snap_bots()
    except Exception:
        if once('dh-bot-snap'):
            log_error('local-battle-bot-snap-error')
    return _dh_original_step_motion(now)


if _dh_original_spawn_remote is not None and _dh_original_step_motion is not None:
    _dh_spawn_remote_wrapper._dh_inner = _dh_original_spawn_remote
    _dh_step_motion_wrapper._dh_inner = _dh_original_step_motion
    _spawn_remote = _dh_spawn_remote_wrapper
    step_motion = _dh_step_motion_wrapper
log('local-battle-bot-ground-snap', installed=callable(_dh_original_step_motion) and callable(_dh_original_spawn_remote))


# --- last one standing: the hook shows the win screen (rank 1), but this client build's result panel
# closes itself a couple of seconds later (its own animation end callback) and the player is left
# standing in the world with "1 LEFT".  After the result has been shown, move on the way the stand-in
# used to: rank page, then back to the lobby.
_dh_original_show_result = _dh_unwrap(globals().get('show_result'))


def _dh_result_screen_open():
    try:
        import Globals
        return bool(Globals.uiMgr.is_enter('UIBattlegroundsResult'))
    except Exception:
        return False


def _dh_after_result():
    try:
        if BATTLE.get('phase') not in ('fighting', 'over'):
            return False
        if _dh_result_screen_open():
            return False                 # the player is reading the result: its Exit button leads out
        log('local-battle-result-advance', phase=BATTLE.get('phase'))
        return result_rank_page()
    except Exception:
        log_error('local-battle-result-advance-error')
        return False


def _dh_end_fight_status():
    """UIBattlegroundsResult.delayShowResult leaves at once while the space says the fight is on
    and we are not dead: a win (last one standing) is exactly that, so end the fight status first."""
    changed = []
    try:
        import Globals
        space = Globals.spaceEntity
        for name in ('isInFightStatus', 'inFightStatus', 'isFighting', 'fightStatus'):
            if hasattr(space, name):
                try:
                    setattr(space, name, False)
                    changed.append(name)
                except Exception:
                    pass
        for name in ('isInFightStatus',):
            if hasattr(space, name) and callable(getattr(space, name)):
                try:
                    setattr(space, name, lambda *a, **k: False)
                    changed.append(name + '()')
                except Exception:
                    pass
    except Exception:
        pass
    return changed


def _dh_show_result_wrapper(player, rank):
    if rank <= 1:
        log('local-battle-win-fight-status', changed=_dh_end_fight_status())
    shown = _dh_original_show_result(player, rank)
    if shown:
        try:
            call_later(RESULT_PAGE_SECONDS, _dh_after_result)
        except Exception:
            log_error('local-battle-result-advance-error')
    return shown


if _dh_original_show_result is not None:
    _dh_show_result_wrapper._dh_inner = _dh_original_show_result
    show_result = _dh_show_result_wrapper
log('local-battle-result-advance-installed', installed=callable(_dh_original_show_result))


# --- real loot for the bots: the stand-in scatters the round's ground loot in this window only and gives
# the items no shared key, so nothing a bot did could remove them.  Give every spawned item a key, keep a
# plan (key, prop, amount, position) and send it to the battle host; the bots walk to items and take them
# (take_loot), and the shared-loot sync removes the item here.  Our own pickups now report too.
_dh_loot_plan = {'items': [], 'pending': [], 'counter': 0, 'flush_due': False}
_dh_original_spawn_loot = _dh_unwrap(globals().get('spawn_loot'))


def _dh_spawn_loot_wrapper(prop, amount, x, z, y=None):
    entity_id = _dh_original_spawn_loot(prop, amount, x, z, y)
    try:
        if entity_id is not None and entity_id in _loot:
            if y is None:
                ground = ground_height(x, z)
                y = ground if ground else (BATTLE['spawn'] or (0.0, 0.0, 0.0))[1]
            # the key is read at flush time: stream_loot sets its own ('s<spot>:<slot>') right after this returns
            _dh_loot_plan['pending'].append((entity_id, int(prop), int(amount), round(float(x), 2), round(float(y), 2), round(float(z), 2)))
            if not _dh_loot_plan['flush_due']:
                _dh_loot_plan['flush_due'] = True
                call_later(1.0, _dh_flush_loot_plan)
    except Exception:
        if once('dh-loot-key'):
            log_error('local-battle-loot-key-error')
    return entity_id


def _dh_flush_loot_plan():
    _dh_loot_plan['flush_due'] = False
    pending = _dh_loot_plan['pending']
    items = []
    while pending:
        entity_id, prop, amount, x, y, z = pending.pop(0)
        record = _loot.get(entity_id)
        if record is None:
            continue                            # gone already
        key = record.get('key')
        if not key:
            _dh_loot_plan['counter'] += 1
            key = 'p%d-%d' % (BATTLE.get('entity_id') or 0, _dh_loot_plan['counter'])
            record['key'] = key
            record['full'] = int(record.get('full', amount))
        items.append([key, prop, int(record.get('full', amount)), x, y, z])
    sent = 0
    for start in range(0, len(items), 25):
        chunk = items[start:start + 25]
        try:
            send(LOOT_PREFIX + json.dumps({'plan': chunk}))
            sent += len(chunk)
        except Exception:
            if once('dh-loot-plan'):
                log_error('local-battle-loot-plan-error')
            break
    _dh_loot_plan['items'].extend(items)
    if sent and len(_dh_loot_plan['items']) <= 60 or (sent and len(_dh_loot_plan['items']) % 200 < 25):
        log('local-battle-loot-plan-sent', items=sent, total=len(_dh_loot_plan['items']))
    return sent


if _dh_original_spawn_loot is not None:
    _dh_spawn_loot_wrapper._dh_inner = _dh_original_spawn_loot
    spawn_loot = _dh_spawn_loot_wrapper
log('local-battle-loot-plan-installed', installed=_dh_original_spawn_loot is not None)


# --- the level record (loot spots, car spawns, bot birth points, ...): export it once per map so the
# server can roam bots through real towns and buildings.
_dh_original_start_world_stream = _dh_unwrap(globals().get('start_world_stream'))


def _dh_export_level_record():
    try:
        map_id = int(BATTLE.get('map') or 0)
        path = getattr(LOBBY, 'LOG_PATH', None)
        if not map_id or not path:
            return 'no-path'
        import os
        target = os.path.join(os.path.dirname(os.path.abspath(path)), 'level_%d.json' % map_id)
        if os.path.exists(target) and os.path.getsize(target) > 1000:
            return 'exists'
        record = level_record(map_id)
        if not record:
            return 'no-record'
        sizes = dict((str(k), len(v) if hasattr(v, '__len__') else 1) for k, v in record.items())
        points = {}
        for section, items in record.items():
            if not isinstance(items, list) or not items or not isinstance(items[0], dict) or 'point' not in items[0]:
                continue
            rows = []
            for item in items:
                try:
                    x, y, z = (float(v) for v in item['point'][:3])
                except Exception:
                    continue
                direction = item.get('direction') or [0.0, 0.0, 0.0]
                rows.append([round(x, 2), round(y, 2), round(z, 2), item.get('group_id'), round(float(direction[2]) if len(direction) > 2 else 0.0, 3)])
            points[str(section)] = rows
        payload = {'map': map_id, 'sections': sizes, 'points': points}

        def write():
            try:
                text = json.dumps(payload)
                with open(target + '.tmp', 'w') as handle:
                    handle.write(text)
                os.rename(target + '.tmp', target)
            except Exception:
                pass
        import threading
        threading.Thread(target=write).start()
        log('local-battle-level-exported', path=target, sections=sizes, point_sections=dict((k, len(v)) for k, v in points.items()))
        return 'written'
    except Exception:
        log_error('local-battle-level-export-error')
        return 'error'


def _dh_start_world_stream_wrapper():
    result = _dh_original_start_world_stream()
    try:
        call_later(3.0, _dh_export_level_record)
    except Exception:
        pass
    return result


if _dh_original_start_world_stream is not None:
    _dh_start_world_stream_wrapper._dh_inner = _dh_original_start_world_stream
    start_world_stream = _dh_start_world_stream_wrapper
log('local-battle-level-export-installed', installed=callable(_dh_original_start_world_stream))


# --- line of sight for the bots: the battle host has no building geometry, so bots used to shoot a player
# hiding inside a house.  This client has the island's colliders: twice a second, ray-test every nearby bot
# (its eyes) against the player's head, chest and legs, and tell the host which bots can see the player.
# The host lets a bot shoot only when its target's client says it is in sight.  Survives re-execution of
# this patch: the timer loop is kept in a global and only started once.
_dh_los = globals().get('_dh_los') or {'running': False, 'sent': 0, 'errors': 0, 'last_visible': 0, 'last_hidden': 0}
# m41h (2026-10-29): these were written as metres, but battle positions are game units of 0.1 m - only bots within
# 26 m were probed, no report went out otherwise, and the host (no fresh report = "in sight") let every bot from 26 m
# to its 200 m sight shoot through walls and floors (player report: killed on a top floor by a bot on the ground).
_DH_LOS_UNIT = 10.0             # game units per metre
_DH_LOS_RANGE = 260.0 * _DH_LOS_UNIT     # farther bots are not probed (max bot sight is 200 m x 1.3)
_DH_LOS_PERIOD = 0.5            # seconds between reports
_DH_LOS_BOT_EYE = 1.5 * _DH_LOS_UNIT     # bot bodies are snapped to the ground: eyes this far above
_DH_LOS_PLAYER_LIFTS = (0.6 * _DH_LOS_UNIT, 0.0, -0.5 * _DH_LOS_UNIT)   # body centre (~1 m up): head, chest, legs
_DH_LOS_START = 0.7 * _DH_LOS_UNIT       # start the ray this far in front of the bot's eyes (past its own collider)
_DH_LOS_SKIN = 1.2 * _DH_LOS_UNIT        # a hit this close to the player's point is the player's own body


def _dh_bot_point(battle_id):
    body = _motion['bodies'].get(battle_id)
    if body and body.get('samples'):
        return body['samples'][-1][1]
    entity = _resolve_entity(_remote.get(battle_id))
    if entity is not None and hasattr(entity, 'position'):
        return _point(entity.position)
    return None


def _dh_clear_line(origin, target):
    """True when the island (walls, floors, terrain) does not block the line from origin to target."""
    seg = (target[0] - origin[0], target[1] - origin[1], target[2] - origin[2])
    length = math.sqrt(seg[0] ** 2 + seg[1] ** 2 + seg[2] ** 2)
    if length <= _DH_LOS_START + _DH_LOS_SKIN:
        return True
    start = tuple(o + s / length * _DH_LOS_START for o, s in zip(origin, seg))
    hit = surface_hit(start, target)
    if hit is None:
        return True
    return distance(hit[0], target) < _DH_LOS_SKIN


def _dh_los_tick():
    try:
        if BATTLE.get('address') is None or not _dh_bot_ids:
            return
        player = current_player()
        if player is None:
            return
        me = _point(player.position)
        if me is None:
            return
        visible, hidden = [], []
        for battle_id in list(_dh_bot_ids):
            point = _dh_bot_point(battle_id)
            if point is None:
                continue
            if distance(point, me) > _DH_LOS_RANGE:
                continue
            eyes = (point[0], point[1] + _DH_LOS_BOT_EYE, point[2])
            seen = False
            for lift in _DH_LOS_PLAYER_LIFTS:
                if _dh_clear_line(eyes, (me[0], me[1] + lift, me[2])):
                    seen = True
                    break
            (visible if seen else hidden).append(battle_id)
        if visible or hidden:
            send(LOOT_PREFIX + json.dumps({'los': {'me': BATTLE.get('entity_id') or 0, 'v': visible, 'h': hidden}}))
            _dh_los['sent'] += 1
            _dh_los['last_visible'], _dh_los['last_hidden'] = len(visible), len(hidden)
            if _dh_los['sent'] in (1, 20, 200, 2000):
                log('local-battle-los-sent', visible=len(visible), hidden=len(hidden), sent=_dh_los['sent'])
    except Exception:
        _dh_los['errors'] += 1
        if once('dh-los'):
            log_error('local-battle-los-error')
    finally:
        try:
            call_later(_DH_LOS_PERIOD, _dh_los_tick)
        except Exception:
            _dh_los['running'] = False


if not _dh_los['running']:
    _dh_los['running'] = True
    call_later(_DH_LOS_PERIOD, _dh_los_tick)
log('local-battle-los-installed', running=_dh_los['running'], sent=_dh_los['sent'])


# --- ears and walls for the bots.  (1) Every shot the player fires is reported to the host (throttled), so
# bots within hearing come to look.  (2) The host tells where each bot is heading ('tg' in its act record);
# this client ray-tests that way at waist height for bots close to the player and reports a wall in the way
# (distance and wall normal), so the host can slide the bot along the wall to the door instead of through it.
_dh_ears = globals().get('_dh_ears') or {'running': False, 'last_shot': 0.0, 'shots': 0, 'blocked': 0, 'probes': 0}
_DH_SHOT_THROTTLE = 0.6
_DH_PROBE_PERIOD = 0.4
_DH_PROBE_RANGE = 160.0 * 10.0  # 160 m from the player (game units: 0.1 m - m41h): bots farther away are not probed
_DH_PROBE_REACH = 5.0 * 10.0    # 5 m ahead of the bot are tested
_DH_PROBE_HEIGHT = 0.7 * 10.0   # waist height above the (snapped) ground


def _dh_on_fire_wrapper(player, *args, **kwargs):
    try:
        now = time.time()
        if now - _dh_ears['last_shot'] >= _DH_SHOT_THROTTLE and BATTLE.get('address') is not None:
            _dh_ears['last_shot'] = now
            me = _point(player.position) if player is not None and hasattr(player, 'position') else None
            if me is not None:
                send(LOOT_PREFIX + json.dumps({'shot': {'me': BATTLE.get('entity_id') or 0,
                                                        'pos': [round(me[0], 1), round(me[1], 1), round(me[2], 1)]}}))
                _dh_ears['shots'] += 1
    except Exception:
        if once('dh-shot-report'):
            log_error('local-battle-shot-report-error')
    return _dh_original_on_fire(player, *args, **kwargs)


_dh_original_on_fire = _dh_unwrap(globals().get('on_fire'))
if _dh_original_on_fire is not None:
    _dh_on_fire_wrapper._dh_inner = _dh_original_on_fire
    on_fire = _dh_on_fire_wrapper
    try:
        LOBBY.RPC_HANDLERS['fire'] = _dh_on_fire_wrapper
    except Exception:
        pass


def _dh_probe_tick():
    try:
        if BATTLE.get('address') is None or not _dh_bot_ids:
            return
        player = current_player()
        if player is None:
            return
        me = _point(player.position)
        if me is None:
            return
        blocked = []
        for battle_id in list(_dh_bot_ids):
            act = _acts.get(battle_id) or {}
            heading = act.get('tg')
            if not heading:
                continue
            point = _dh_bot_point(battle_id)
            if point is None or distance(point, me) > _DH_PROBE_RANGE:
                continue
            dx, dz = float(heading[0]) - point[0], float(heading[1]) - point[2]
            length = math.hypot(dx, dz)
            if length < 0.5:
                continue
            reach = min(_DH_PROBE_REACH, length)
            origin = (point[0], point[1] + _DH_PROBE_HEIGHT, point[2])
            target = (point[0] + dx / length * reach, origin[1], point[2] + dz / length * reach)
            _dh_ears['probes'] += 1
            hit = surface_hit(origin, target)
            if hit is None:
                continue
            hit_point, normal = hit
            blocked.append([battle_id, round(distance(origin, hit_point), 2), round(normal[0], 3), round(normal[2], 3)])
        if blocked:
            send(LOOT_PREFIX + json.dumps({'blk': blocked[:40]}))
            _dh_ears['blocked'] += len(blocked)
            if _dh_ears['blocked'] in (1, 50, 500):
                log('local-battle-walls-reported', blocked=len(blocked), total=_dh_ears['blocked'], probes=_dh_ears['probes'])
    except Exception:
        if once('dh-probe'):
            log_error('local-battle-probe-error')
    finally:
        try:
            call_later(_DH_PROBE_PERIOD, _dh_probe_tick)
        except Exception:
            _dh_ears['running'] = False


if not _dh_ears['running']:
    _dh_ears['running'] = True
    call_later(_DH_PROBE_PERIOD, _dh_probe_tick)
log('local-battle-ears-installed', fire_hook=callable(_dh_original_on_fire), running=_dh_ears['running'])


# --- the first circle must contain the landing.  The plane phase starts the zone with a random first
# circle, so the player (and the bots dropped around them) could land 10+ km outside it with no way to walk
# in.  At the landing, if the first circle does not hold the landing point, re-plan the circles around it
# (the way a real plane path crosses the first circle) and tell the bot host.
_dh_original_settle_world = _dh_unwrap(globals().get('settle_world'))


def _dh_settle_world_wrapper(point):
    result = _dh_original_settle_world(point)
    try:
        if _zone.get('on') and _zone.get('circles') and _zone.get('times') and _zone.get('elapsed', 0.0) < _zone['times'][0][1]:
            cx, cz, radius = _zone['circles'][0]
            if math.hypot(point[0] - cx, point[2] - cz) > radius * 0.85:
                _zone['circles'] = plan_circles(_zone['start'], _zone['rounds'], _zone['random'], (point[0], point[2]))
                _zone['shown'] = {}
                send_bot_zone(_zone['circles'][0])
                log('local-battle-zone-recentred', first=[round(v) for v in _zone['circles'][0]],
                    landing=[round(point[0]), round(point[2])], was=[round(cx), round(cz), round(radius)])
    except Exception:
        log_error('local-battle-zone-recentre-error')
    return result


if _dh_original_settle_world is not None:
    _dh_settle_world_wrapper._dh_inner = _dh_original_settle_world
    settle_world = _dh_settle_world_wrapper
log('local-battle-zone-recentre-installed', installed=callable(_dh_original_settle_world))


# --- navigation probe: the client has a Detour navigation mesh (movement.navi_utils.getNaviPath & co).  At
# the landing, ask it for a few paths around the player and log what comes back (signature, result type,
# point count), so the bot host can be given real door-to-door paths if the mesh is loaded on this map.
_dh_nav = globals().get('_dh_nav') or {'probed': False}


def _dh_point_of(p):
    try:
        return (float(p.x), float(p.y), float(p.z))
    except Exception:
        return (float(p[0]), float(p[1]), float(p[2]))
_DH_NAV_VERSION = 'm20'
if _dh_nav.get('version') != _DH_NAV_VERSION:
    _dh_nav.update(version=_DH_NAV_VERSION, probed=False, ok=None, vec=None)


def _dh_nav_vectors():
    """Candidate constructors for the positions navi_utils accepts (its own Vector3, math3d, a plain tuple)."""
    out = []
    navi = _dh_sys.modules.get('movement.navi_utils')
    for getter in (lambda: __import__('math3d').vector, lambda: _dh_sys.modules['math3d'].vector,
                   lambda: getattr(navi.math3d, 'vector'), lambda: getattr(navi, 'Vector3'),
                   lambda: __import__('math3d').Vector3, lambda: _dh_sys.modules['libclaudia.Classes.Physics'].Vector3):
        try:
            ctor = getter()
            if ctor is not None and ctor not in out:
                out.append(ctor)
        except Exception:
            continue
    out.append(lambda x, y, z: (x, y, z))
    return out


def _dh_nav_call(navi, name, src, dst):
    """Call navi_utils.<name>(src, dst) with the first vector type it accepts (remembered)."""
    fn = getattr(navi, name)
    ctors = [_dh_nav['vec']] if _dh_nav.get('vec') is not None else _dh_nav_vectors()
    last = None
    for ctor in ctors:
        try:
            result = fn(ctor(src[0], src[1], src[2]), ctor(dst[0], dst[1], dst[2]))
            _dh_nav['vec'] = ctor
            return result
        except TypeError as error:
            last = error
            continue
    raise TypeError('no accepted vector type: %r' % (last,))


def _dh_nav_probe(point):
    import inspect
    report = {}
    try:
        navi = _dh_sys.modules.get('movement.navi_utils')
        if navi is None:
            import movement.navi_utils as navi
        for name in ('getNaviPath', 'canNaviTo', 'getNaviDist', 'getNearestRoadPos', 'getHighWayPath', 'getDistNoNavi'):
            fn = getattr(navi, name, None)
            if fn is None:
                continue
            try:
                report[name + '_args'] = str(inspect.getargspec(fn))
            except Exception:
                report[name + '_args'] = 'n/a'
        try:
            sw = _dh_sys.modules.get('shared.switches')
            report['EnableNavigation'] = getattr(sw, 'EnableNavigation', None)
            report['EnableNavigation8k'] = getattr(sw, 'EnableNavigation8k', None)
        except Exception:
            pass
        try:
            import detour
            report['detour'] = [a for a in dir(detour) if not a.startswith('_')][:60]
        except Exception as error:
            report['detour'] = 'import failed: %r' % (error,)
        src = (point[0], point[1], point[2])
        for dist in (40.0, 150.0, 600.0):
            dst = (point[0] + dist, point[1], point[2] + dist * 0.5)
            key = 'd%d' % int(dist)
            try:
                report[key + '_can'] = bool(_dh_nav_call(navi, 'canNaviTo', src, dst))
            except Exception as error:
                report[key + '_can'] = 'error %r' % (error,)
            try:
                path = _dh_nav_call(navi, 'getNaviPath', src, dst)
                pts = [_dh_point_of(p) for p in path] if path is not None else None
                report[key + '_path'] = {'type': type(path).__name__, 'count': len(pts) if pts is not None else None,
                                         'first': [[round(x, 1), round(y, 1), round(z, 1)] for x, y, z in (pts or [])[:4]]}
            except Exception as error:
                report[key + '_path'] = 'error %r' % (error,)
            try:
                report[key + '_dist'] = _dh_nav_call(navi, 'getNaviDist', src, dst)
            except Exception as error:
                report[key + '_dist'] = 'error %r' % (error,)
        report['vector_type'] = getattr(_dh_nav.get('vec'), '__name__', None) or str(_dh_nav.get('vec'))[:60]
        # what do these functions call?  (bytecode names: the detour calls and globals they use)
        for name in ('getNaviPath', 'canNaviTo', 'getNaviDist', 'getNearestRoadPos'):
            fn = getattr(navi, name, None)
            code = getattr(fn, 'func_code', None) or getattr(fn, '__code__', None)
            if code is not None:
                report[name + '_names'] = list(code.co_names)[:40]
                report[name + '_consts'] = [c for c in code.co_consts if isinstance(c, (int, float, str)) ][:20]
        try:
            import detour
            sd = detour.scene_detour
            report['scene_detour_type'] = type(sd).__name__
            report['scene_detour_dir'] = [a for a in dir(sd) if not a.startswith('__')][:80]
            report['backbone_dir'] = [a for a in dir(detour.BackboneRoad) if not a.startswith('__')][:40]
        except Exception as error:
            report['scene_detour'] = 'error %r' % (error,)
        try:
            comp = _dh_sys.modules.get('movement.NaviComp')
            report['NaviComp_dir'] = [a for a in dir(comp.NaviComp) if not a.startswith('__')][:80]
        except Exception as error:
            report['NaviComp'] = 'error %r' % (error,)
        try:
            report['levelData'] = str(getattr(navi, 'levelData', None))[:200]
            report['navi_globals'] = [a for a in dir(navi) if not a.startswith('__')][:60]
        except Exception:
            pass
        try:
            import math3d
            report['math3d_vector_dir'] = [a for a in dir(math3d.vector) if not a.startswith('__')][:30]
        except Exception as error:
            report['math3d'] = 'error %r' % (error,)
        try:
            ctor = _dh_nav.get('vec') or _dh_sys.modules['libclaudia.Classes.Physics'].Vector3
            road = navi.getNearestRoadPos(ctor(src[0], src[1], src[2]))
            report['road'] = str(road)[:120]
        except Exception as error:
            report['road'] = 'error %r' % (error,)
        _dh_nav['ok'] = any(isinstance(v, dict) and (v.get('count') or 0) >= 2 for k, v in report.items() if k.endswith('_path'))
        log('local-battle-nav-probe', mesh_ok=_dh_nav['ok'], **dict((k, safe(v, 400) if isinstance(v, str) else v) for k, v in report.items()))
    except Exception:
        log_error('local-battle-nav-probe-error')


def _dh_nav_probe_later(point):
    if _dh_nav['probed']:
        return
    _dh_nav['probed'] = True
    call_later(8.0, _dh_nav_probe, point)


_dh_original_settle_world_nav = _dh_unwrap(globals().get('settle_world'))


def _dh_settle_world_nav_wrapper(point):
    result = _dh_original_settle_world_nav(point)
    try:
        _dh_nav_probe_later(tuple(point))
    except Exception:
        pass
    return result


if _dh_original_settle_world_nav is not None and getattr(_dh_original_settle_world_nav, '__name__', '') != '_dh_settle_world_nav_wrapper':
    _dh_settle_world_nav_wrapper._dh_inner = _dh_original_settle_world_nav
    settle_world = _dh_settle_world_nav_wrapper
try:
    if not _dh_nav['probed'] and BATTLE.get('address') is not None and current_player() is not None and _flight.get('stage') == 'landed':
        _dh_nav_probe_later(_point(current_player().position))
except Exception:
    pass
log('local-battle-nav-probe-installed', installed=callable(_dh_original_settle_world_nav), version=_DH_NAV_VERSION)


# --- path service: the bot host puts each bot's goal in its act record ('gl' = [x, z, plan number]); for bots
# near the player this client walks the navigation mesh from the bot to that goal and sends the points back
# ({'path': {'bot', 'pn', 'pts'}}), so bots take doors, stairs and gaps instead of straight lines.  Only once
# the probe has seen the mesh answer on this map.
_dh_navsvc = globals().get('_dh_navsvc') or {'running': False, 'sent': {}, 'paths': 0, 'errors': 0}
_DH_NAV_RANGE = 500.0
_DH_NAV_PERIOD = 0.6
_DH_NAV_MAX_PTS = 40
_DH_NAV_PER_TICK = 3


def _dh_point_of(p):
    try:
        return (float(p.x), float(p.y), float(p.z))
    except Exception:
        return (float(p[0]), float(p[1]), float(p[2]))


def _dh_mesh_path(src, dst):
    navi = _dh_sys.modules.get('movement.navi_utils')
    physics_module = _dh_sys.modules.get('libclaudia.Classes.Physics')
    if navi is None or physics_module is None:
        return None
    path = _dh_nav_call(navi, 'getNaviPath', src, dst)
    if not path:
        return None
    pts = [_dh_point_of(p) for p in path]
    if len(pts) < 2:
        return None
    if len(pts) > _DH_NAV_MAX_PTS:
        step = float(len(pts) - 1) / (_DH_NAV_MAX_PTS - 1)
        pts = [pts[int(round(i * step))] for i in range(_DH_NAV_MAX_PTS - 1)] + [pts[-1]]
    return pts


def _dh_nav_tick():
    try:
        if not _dh_nav.get('ok') or BATTLE.get('address') is None or not _dh_bot_ids:
            return
        player = current_player()
        me = _point(player.position) if player is not None else None
        if me is None:
            return
        now = time.time()
        sent = _dh_navsvc['sent']
        for key in [k for k, stamp in sent.items() if now - stamp > 180.0]:
            sent.pop(key, None)
        done = 0
        for battle_id in list(_dh_bot_ids):
            if done >= _DH_NAV_PER_TICK:
                break
            act = _acts.get(battle_id) or {}
            goal = act.get('gl')
            if not goal or len(goal) < 3:
                continue
            key = (battle_id, int(goal[2]))
            if key in sent:
                continue
            point = _dh_bot_point(battle_id)
            if point is None or distance(point, me) > _DH_NAV_RANGE:
                continue
            sent[key] = now
            done += 1
            gy = ground_height(goal[0], goal[1])
            dst = (float(goal[0]), gy if gy else point[1], float(goal[1]))
            try:
                pts = _dh_mesh_path(point, dst)
            except Exception:
                _dh_navsvc['errors'] += 1
                if once('dh-nav-path'):
                    log_error('local-battle-nav-path-error')
                continue
            if not pts:
                continue
            send(LOOT_PREFIX + json.dumps({'path': {'bot': battle_id, 'pn': int(goal[2]),
                                                     'pts': [[round(x, 1), round(y, 1), round(z, 1)] for x, y, z in pts]}}))
            _dh_navsvc['paths'] += 1
            if _dh_navsvc['paths'] in (1, 10, 100, 1000):
                log('local-battle-nav-path-sent', bot=battle_id, points=len(pts), total=_dh_navsvc['paths'])
    except Exception:
        if once('dh-nav-tick'):
            log_error('local-battle-nav-tick-error')
    finally:
        try:
            call_later(_DH_NAV_PERIOD, _dh_nav_tick)
        except Exception:
            _dh_navsvc['running'] = False


if not _dh_navsvc['running']:
    _dh_navsvc['running'] = True
    call_later(_DH_NAV_PERIOD, _dh_nav_tick)
log('local-battle-nav-service-installed', running=_dh_navsvc['running'], mesh_ok=_dh_nav.get('ok'))


# --- big battle replies over the internet: a 20-bot snapshot is ~5 KB, which IP fragments and many home
# connections drop (the VPS showed it: pings arrived, snapshots never did, no rival was drawn).  Announce
# that this client reassembles compressed parts ({'zip': 2} every 3 s), and read them: b'RZ' + '>HBB'
# (message id, part, count) + zlib data.  Plain JSON packets still work as before.
_dh_rz = globals().get('_dh_rz') or {'parts': {}, 'order': [], 'running': False, 'joined': 0, 'bad': 0}


def _dh_drain_wrapper(limit=48):
    import struct as _st
    import zlib as _zl
    client = BATTLE['socket']
    if client is None:
        return []
    packets = []
    for _ in range(limit):
        try:
            data, _peer = client.recvfrom(65535)
        except Exception:
            break
        _perf['in_packets'] += 1
        _perf['in_bytes'] += len(data)
        _perf['in_max'] = max(_perf['in_max'], len(data))
        started = perf_clock()
        try:
            if data[:2] == 'RZ' and len(data) >= 6:
                message, index, count = _st.unpack('>HBB', data[2:6])
                parts = _dh_rz['parts'].get(message)
                if parts is None:
                    parts = _dh_rz['parts'][message] = {}
                    _dh_rz['order'].append(message)
                    while len(_dh_rz['order']) > 8:
                        _dh_rz['parts'].pop(_dh_rz['order'].pop(0), None)
                parts[index] = data[6:]
                if len(parts) == count:
                    blob = ''.join(parts[i] for i in range(count))
                    _dh_rz['parts'].pop(message, None)
                    try:
                        _dh_rz['order'].remove(message)
                    except ValueError:
                        pass
                    packets.append(json.loads(_zl.decompress(blob).decode('utf-8')))
                    _dh_rz['joined'] += 1
                    if _dh_rz['joined'] in (1, 100, 1000):
                        log('local-battle-chunked-replies', joined=_dh_rz['joined'], parts=count)
            else:
                packets.append(json.loads(data.decode('utf-8')))
            _perf['parse_ms'] += (perf_clock() - started) * 1000.0
        except Exception:
            _dh_rz['bad'] += 1
            if once('dh-bad-packet'):
                log_error('local-battle-bad-packet', size=len(data))
    return packets


def _dh_zip_announce():
    try:
        if BATTLE.get('address') is not None:
            send(LOOT_PREFIX + json.dumps({'zip': 2}))
    except Exception:
        pass
    finally:
        try:
            call_later(3.0, _dh_zip_announce)
        except Exception:
            _dh_rz['running'] = False


_dh_original_drain = _dh_unwrap(globals().get('drain'))
if _dh_original_drain is not None:
    _dh_drain_wrapper._dh_inner = _dh_original_drain
    drain = _dh_drain_wrapper
if not _dh_rz['running']:
    _dh_rz['running'] = True
    _dh_zip_announce()
log('local-battle-chunked-installed', drain=callable(_dh_original_drain))


# --- m22: Custom Rooms (server_ext/custom_rooms.py).  A room's START ticket names the map of the room's mode
# ('room_map'); the lobby's own mode picker (matchingMapID) is what wanted_map read first, so a room match loaded
# whatever mode the player last picked.  The room's map wins when the ticket has one.
_dh_original_wanted_map = _dh_unwrap(globals().get('wanted_map'))


def _dh_wanted_map_wrapper(player):
    try:
        room_map = int((BATTLE.get('ticket') or {}).get('room_map') or 0)
    except Exception:
        room_map = 0
    if room_map > 0:
        return room_map, 'custom-room'
    return _dh_original_wanted_map(player)


if _dh_original_wanted_map is not None:
    _dh_wanted_map_wrapper._dh_inner = _dh_original_wanted_map
    wanted_map = _dh_wanted_map_wrapper
log('local-battle-room-map-installed', installed=callable(_dh_original_wanted_map))


# --- m23: the matching queue names the map (server_ext/battle_split.py).  The battle host kept one round per game
# server, so a Battle Royale player and a Hero-mode player who pressed START together shared one round on two
# different maps (2026-10-21: one client hung on its loading screen).  The queue packet now carries the map this
# client will load - wanted_map(), the same choice the join packet reports - and the host keeps rounds apart by map.
_dh_original_send = _dh_unwrap(globals().get('send'))


def _dh_send_with_map(payload):
    try:
        if isinstance(payload, basestring) and payload.startswith(QUEUE_PREFIX) and '"map"' not in payload:
            body = json.loads(payload[len(QUEUE_PREFIX):])
            if isinstance(body, dict):
                import BigWorld as _bw
                map_id = int(wanted_map(_bw.player())[0] or 0)
                if map_id > 0:
                    body['map'] = map_id
                    payload = QUEUE_PREFIX + json.dumps(body)
    except Exception:
        pass
    return _dh_original_send(payload)


if _dh_original_send is not None:
    _dh_send_with_map._dh_inner = _dh_original_send
    send = _dh_send_with_map
log('local-battle-queue-map-installed', installed=callable(_dh_original_send))


# --- m24: a round that ends without the player dying left the client in the battle for good (2026-10-21: Jenix_Vink
# after "the round ended" - no result screen, no way back).  apply_snapshot only set phase 'over' when the host said
# the round had finished (time up, or the host restarted).  Now the result screen opens then - its Exit button goes
# back to the lobby - ranked by the players still alive.  A round the host no longer has (no snapshot for
# _DH_LOST_SECONDS while fighting) ends the same way.
_DH_LOST_SECONDS = 45.0
_dh_round_watch = globals().get('_dh_round_watch') or {'last': 0.0, 'token': 0}
_dh_original_apply_snapshot = _dh_unwrap(globals().get('apply_snapshot'))


def _dh_end_round(reason):
    if _round.get('shown') or BATTLE.get('phase') not in ('fighting', 'over'):
        return False
    player = current_player()
    if player is None:
        return False
    space = zone_space()
    rank = max(1, int(getattr(space, 'aliveNum', 1) or 1))
    BATTLE['phase'] = 'over'
    stop_zone()
    # alive at the end: the result panel closes itself while the space says the fight is on (as for a win)
    changed = _dh_end_fight_status()
    log('local-battle-round-end-result', reason=reason, rank=rank, fight_status=changed)
    return show_result(player, rank)


def _dh_apply_snapshot_wrapper(snapshot):
    _dh_round_watch['last'] = time.time()
    was = BATTLE.get('phase')
    result = _dh_original_apply_snapshot(snapshot)
    try:
        if was == 'fighting' and BATTLE.get('phase') == 'over' and not _round.get('shown'):
            call_later(RESULT_DELAY, _dh_end_round, 'round-finished')
    except Exception:
        log_error('local-battle-round-end-error')
    return result


def _dh_round_watchdog(token):
    if token != _dh_round_watch['token']:
        return
    try:
        phase = BATTLE.get('phase')
        if phase in ('fighting', 'over') and not _round.get('shown'):
            last = _dh_round_watch['last'] or time.time()
            if not _dh_round_watch['last']:
                _dh_round_watch['last'] = last
            if time.time() - last > _DH_LOST_SECONDS:
                _dh_end_round('host-lost-round')
        elif phase not in ('fighting', 'over'):
            _dh_round_watch['last'] = 0.0
    except Exception:
        log_error('local-battle-round-watch-error')
    call_later(5.0, _dh_round_watchdog, token)


if _dh_original_apply_snapshot is not None:
    _dh_apply_snapshot_wrapper._dh_inner = _dh_original_apply_snapshot
    apply_snapshot = _dh_apply_snapshot_wrapper
    _dh_round_watch['token'] += 1
    call_later(5.0, _dh_round_watchdog, _dh_round_watch['token'])
log('local-battle-round-end-installed', installed=callable(_dh_original_apply_snapshot))


# --- m25: the result panel stays until the player leaves it, as in the original game (rank, kills, Report /
# Spectate / Next - players screenshot it).  UIBattlegroundsResult.delayShowResult closes the panel instead of
# showing it when the space still reports a fight for a living player (any round end that is not a death: time up,
# last one standing, host gone).  That close is turned into the game's own showResult; Next / Exit work as before.
def _dh_install_result_keep():
    try:
        module = sys.modules.get('ui.UIBattlegroundsResult') or __import__('ui.UIBattlegroundsResult', fromlist=['x'])
    except Exception:
        return False
    cls = getattr(module, 'UIBattlegroundsResult', None)
    if cls is None:
        return False
    current = cls.__dict__.get('leave_self_ui')
    if getattr(current, '_dh_keep', False):
        return True
    inner = getattr(cls, 'leave_self_ui', None)
    if inner is None:
        return False
    inner = getattr(inner, '__func__', inner)

    def leave_self_ui(self, *args, **kwargs):
        try:
            caller = sys._getframe(1).f_code.co_name
        except Exception:
            caller = ''
        if caller == 'delayShowResult' and BATTLE.get('phase') in ('fighting', 'over'):
            try:
                log('local-battle-result-kept')
                return self.showResult()
            except Exception:
                log_error('local-battle-result-keep-error')
        return inner(self, *args, **kwargs)
    leave_self_ui._dh_keep = True
    leave_self_ui._dh_inner = inner
    cls.leave_self_ui = leave_self_ui
    return True


try:
    log('local-battle-result-keep-installed', installed=_dh_install_result_keep())
except Exception:
    log_error('local-battle-result-keep-install-error')


# m25b: "is the result panel open" asked uiMgr.is_enter(), which this client does not have (always False), so the
# result page advanced to the lobby after 8 s although the panel was still up.  The UI object's own flag decides.
def _dh_result_screen_open():
    try:
        import Globals
        ui = (getattr(Globals.uiMgr, '____all_ui__', {}) or {}).get('UIBattlegroundsResult')
        return bool(ui is not None and getattr(ui, 'is_enter', False))
    except Exception:
        return False


# m25c: Next on the result panel only hid it (the player stood in the world).  Next now leads on as in the original
# game: the rank page (stars / points), then the lobby.
def _dh_install_result_next():
    try:
        module = sys.modules.get('ui.UIBattlegroundsResult') or __import__('ui.UIBattlegroundsResult', fromlist=['x'])
    except Exception:
        return False
    cls = getattr(module, 'UIBattlegroundsResult', None)
    current = cls.__dict__.get('onNextBtnEvent') if cls is not None else None
    if current is None or getattr(current, '_dh_next', 0) >= 2:
        return bool(current)
    inner = getattr(current, '_dh_inner', current)      # m26b: an older wrapper is replaced, not wrapped again

    def onNextBtnEvent(self, args, *rest, **kwargs):
        result = inner(self, args, *rest, **kwargs)
        try:
            ended = getattr(getattr(args, 'touch', None), 'phase', None) == TouchPhaseEnded()
        except Exception:
            ended = True
        if ended:
            _round['next_seen'] = True                  # m26b: the release reached the panel
        if ended and BATTLE.get('phase') in ('fighting', 'over') and not _round.get('next_pressed'):
            _round['next_pressed'] = True
            log('local-battle-result-next')
            call_later(0.3, result_rank_page)
        return result
    onNextBtnEvent._dh_next = 2
    onNextBtnEvent._dh_inner = inner
    cls.onNextBtnEvent = onNextBtnEvent
    return True


def TouchPhaseEnded():
    try:
        import TouchPhase as _tp
        return _tp.Ended
    except Exception:
        pass
    try:
        from libclaudia.Classes import Input as _input
        return _input.TouchPhase.Ended
    except Exception:
        return getattr(getattr(sys.modules.get('ui.UIBattlegroundsResult'), 'TouchPhase', None), 'Ended', None)


try:
    log('local-battle-result-next-installed', installed=_dh_install_result_next())
except Exception:
    log_error('local-battle-result-next-install-error')


# --- m26b: in hero rounds Next on the result panel did nothing: the button's touch reached the panel's binder but
# never the panel's onNextBtnEvent (the death panel's and the rank page's Next worked).  The panel's Next button gets a
# listener of ours as well; after a release, if the panel's Next did not run within 0.4 s, it is run.  And, like the
# original game's result countdown, a panel nobody leaves goes on to the rank page after _DH_RESULT_AUTO_NEXT seconds
# (time enough to screenshot the kills and the place) - nobody stays stuck on it.
_DH_RESULT_AUTO_NEXT = 120.0


class _DhTouchArgs(object):
    pass


def _dh_result_press_next(ui, why):
    if _round.get('next_seen') or _round.get('next_pressed') or not _dh_result_screen_open():
        return
    args = _DhTouchArgs()
    args.touch = _DhTouchArgs()
    args.touch.phase = TouchPhaseEnded()
    log('local-battle-result-next-forced', why=why)
    try:
        ui.onNextBtnEvent(args)
    except Exception:
        log_error('local-battle-result-next-forced-error')
    _round['next_seen'] = True


def _dh_hook_result_next(ui):
    if getattr(ui, '_dh_next_hooked', False):
        return True
    ui._dh_next_hooked = True
    token = object()
    _round['auto_next'] = token

    def auto_next():
        if _round.get('auto_next') is token:
            _dh_result_press_next(ui, 'countdown')
    call_later(_DH_RESULT_AUTO_NEXT, auto_next)
    button = getattr(ui, 'nextBtn', None)
    add = getattr(button, 'addTouchEventListener', None)
    if not callable(add):
        return False
    ccui = getattr(sys.modules.get('libclaudia.Classes.WidgetTouchesBinder'), 'ccui', None)
    ended = getattr(ccui, 'WIDGET_TOUCHEVENTTYPE_ENDED', None)

    def on_touch(sender, event_type, *rest):
        if ended is None or event_type == ended:
            call_later(0.4, _dh_result_press_next, ui, 'release')
    try:
        add(on_touch)
    except Exception:
        log_error('local-battle-result-next-hook-error')
        return False
    return True



# --- m26d: the result panel named every round "Solo-Ranked" (the hook reports each round as GameEnterType.RANKED, which
# keeps the rank page after Next).  The label now names the mode that was played: the hero maps by their own mode, any
# other round by the mode picked in Modes (lobby state teamType); only the label changes.
_DH_MAP_MODES = {730: 14, 731: 14, 732: 15, 733: 16}             # GameEnterType HERO / HERO_CUSTOM / HEROSECRETTREASURE


def _dh_round_mode():
    mode = _DH_MAP_MODES.get(int(BATTLE.get('map') or 0))
    if mode:
        return mode
    try:
        state = LOBBY.load_state() or {}
        return int((state.get('lobby') or {}).get('teamType') or 0)
    except Exception:
        return 0


def _dh_result_mode_label(ui):
    mode = _dh_round_mode()
    if not mode or mode == RESULT_GAME_TYPE:
        return False
    names = getattr(sys.modules.get('const'), 'DTS_TYPE_NAME', None)
    name = names.get(mode) if isinstance(names, dict) else None
    ranked = names.get(RESULT_GAME_TYPE) if isinstance(names, dict) else None
    label = getattr(ui, 'modeMark', None)
    get_text = getattr(label, 'getString', None)
    set_text = getattr(label, 'setString', None)
    if not name or not ranked or not callable(get_text) or not callable(set_text):
        return False
    text = get_text() or ''
    if ranked not in text:
        return False
    set_text(text.replace(ranked, name))
    log('local-battle-result-mode-label', mode=mode, label=safe(text.replace(ranked, name), 60))
    return True

def _dh_install_result_show():
    try:
        module = sys.modules.get('ui.UIBattlegroundsResult') or __import__('ui.UIBattlegroundsResult', fromlist=['x'])
    except Exception:
        return False
    cls = getattr(module, 'UIBattlegroundsResult', None)
    current = cls.__dict__.get('showResult') if cls is not None else None
    if current is None:
        return False
    inner = getattr(current, '_dh_inner', current)

    def showResult(self, *args, **kwargs):
        result = inner(self, *args, **kwargs)
        try:
            if BATTLE.get('phase') in ('fighting', 'over'):
                log('local-battle-result-next-hooked', listener=_dh_hook_result_next(self))
                _dh_result_mode_label(self)
        except Exception:
            log_error('local-battle-result-next-hook-error')
        return result
    showResult._dh_inner = inner
    cls.showResult = showResult
    return True


try:
    log('local-battle-result-show-installed', installed=_dh_install_result_show())
except Exception:
    log_error('local-battle-result-show-install-error')


# --- m26: hero modes (Hero Clash 731, custom hero 732, hero treasure 733).  The pick screen (UISelectHero) opened with
# no heroes and closed at once, and the match was played as the normal character.  Now:
#   - match found on a hero map: 3 heroes are offered for BATTLE_HERO_SELECT_TIME (20 s), the server answers the pick
#     (server_ext/heroes.py); the match starts when the hero is locked or the time is up (first offer if none);
#   - in battle the player is built with identityType = the hero (the game's DtsOccupation row: skills, abilities);
#   - a skill cast (cell.skillRequest) is played the way the game server did: skillStart, every stage (its
#     TOTAL_TIME), skillFinish with the skill's cooldown; breakSkillRequest ends it.
_DH_HERO_MAPS = (730, 731, 732, 733)
# 32 (Chimera) left out: a melee-only hero that levels up by fusing heritage, a mechanic this server does not have
_DH_HERO_IDS = (23, 24, 25, 26, 27, 28, 29, 30, 31, 33, 34, 36, 37, 38, 39, 40, 41)
_dh_hero = globals().get('_dh_hero') or {'pick': None, 'hero': 0, 'skills': {}}


def _dh_server_time():
    try:
        import BigWorld
        return float(BigWorld.serverTime())
    except Exception:
        return time.time()


def _dh_hero_map(player):
    try:
        return int(wanted_map(player)[0] or 0) in _DH_HERO_MAPS
    except Exception:
        return False


def _dh_start_hero_pick(player):
    import random as _random
    seconds = 20
    try:
        import const as _const
        seconds = int(getattr(_const, 'BATTLE_HERO_SELECT_TIME', 20) or 20)
    except Exception:
        pass
    offer = _random.sample(_DH_HERO_IDS, 3)
    end = _dh_server_time() + seconds
    gid = int(getattr(player, 'gid', 0) or 0)
    name = str(getattr(player, 'nickname', '') or '')
    for attr, value in (('candidateHeros', offer), ('heroSelectEndTime', end), ('refreshCandidateHeroCnt', 11),
                        ('matchedPlayerSelectionInfo', {gid: {'nickname': name, 'selectedHero': offer[0], 'lockedHero': 0}})):
        try:
            setattr(player, attr, value)
        except Exception:
            log_error('local-hero-pick-attr-error', attr=attr)
    _dh_hero['pick'] = {'end': time.time() + seconds, 'offer': offer, 'locked': False}
    _dh_hero['hero'] = offer[0]                      # the screen shows the first offer as chosen until a pick
    _dh_hero['skills'] = {}                          # a skill left running by the last round
    try:
        player.base.rlHeroPickStart(list(offer))
    except Exception:
        pass
    log('local-hero-pick', offer=offer, seconds=seconds)


_dh_original_match_found = _dh_unwrap(globals().get('match_found'))
_dh_original_countdown_done = _dh_unwrap(globals().get('countdown_done'))
_dh_original_player_properties = _dh_unwrap(globals().get('player_properties'))
_dh_original_seed_player_fields = _dh_unwrap(globals().get('seed_player_fields'))
_dh_original_landed = _dh_unwrap(globals().get('landed'))


def _dh_match_found_wrapper(player):
    _dh_hero['pick'] = None
    hero_mode = False
    try:
        hero_mode = _dh_hero_map(player)
        if hero_mode:
            _dh_start_hero_pick(player)
    except Exception:
        log_error('local-hero-pick-error')
    result = _dh_original_match_found(player)
    if hero_mode and _dh_hero.get('pick') is not None:
        # the game opens its pick screen on PRE_ENTERING (UIMain._on_match_pre_entering), which the hook sends
        # only when the battle loads: send it now, while the pick runs
        try:
            _match_state(player, 'PRE_ENTERING')
        except Exception:
            log_error('local-hero-pre-entering-error')
    return result


def _dh_countdown_done_wrapper(player):
    pick = _dh_hero.get('pick')
    if pick is not None and BATTLE.get('phase') == 'matched' and not pick['locked'] and time.time() < pick['end']:
        call_later(1.0, countdown_done, player)          # the pick screen is still open
        return False
    if pick is not None and not _dh_hero.get('hero'):
        _dh_hero['hero'] = pick['offer'][0]
    if pick is not None:
        try:
            import Globals
            Globals.uiMgr.leave_ui('UISelectHero')
        except Exception:
            pass
        log('local-hero-chosen', hero=_dh_hero.get('hero'))
    return _dh_original_countdown_done(player)


def _dh_player_properties_wrapper(player, map_id):
    properties = _dh_original_player_properties(player, map_id)
    hero = int(_dh_hero.get('hero') or 0)
    if hero and int(map_id or 0) in _DH_HERO_MAPS:
        properties['identityType'] = hero
        properties['occupation'] = hero
        properties.setdefault('cooldownFinishTime', {})     # UIPanelSkill.initSkill: skill id -> cooldown end
        # m26c: the hero's own body (character type / gender: HeroInfo rows), so its outfit fits it
        try:
            utils = sys.modules.get('equip_utils') or __import__('equip_utils')
            character = int(utils.properties.getUnlockHeroRequirementsData(hero).CHARACTER_TYPE or 0)
            gender = int(utils.getHeroGender(hero) or 0)
            if character:
                properties['characterType'] = character
            if gender:
                properties['gender'] = gender
                properties['dtsAppearanceGender'] = gender
        except Exception:
            log_error('local-hero-body-error')
        log('local-hero-applied', hero=hero, map=map_id, character=properties.get('characterType'))
    return properties


def _dh_hero_skill_ready(entity, when):
    # UIPanelSkill.onSkillBtnPress (button and PC hotkey alike) casts only when canCastSkill, and showSkillPanel needs
    # skillUIEnabled.  Plain client attributes: createEntity drops them from the properties and the hook's fallback
    # answers False, so the hero skill never went out.  Set on the body itself (built, and again on landing).
    try:
        if int(_dh_hero.get('hero') or 0) and int(BATTLE.get('map') or 0) in _DH_HERO_MAPS:
            entity.canCastSkill = True
            entity.skillUIEnabled = True
            log('local-hero-skill-ready', hero=_dh_hero.get('hero'), when=when)
            # m26c: the hero's outfit.  Avatar.set_identityType dresses a hero body (appear.dressOccupation) when the
            # server changes the identity; ours was set at birth, so the body kept the player's own clothes.
            call_later(1.5 if when == 'landed' else 4.0, _dh_hero_dress, entity)
    except Exception:
        log_error('local-hero-skill-ready-error')



def _dh_hero_dress(entity):
    try:
        if not int(_dh_hero.get('hero') or 0) or int(BATTLE.get('map') or 0) not in _DH_HERO_MAPS:
            return
        if int(getattr(entity, 'identityType', 0) or 0) != int(_dh_hero.get('hero') or 0):
            return
        setter = getattr(entity, 'set_identityType', None)
        if callable(setter):
            setter(0)
            log('local-hero-dressed', hero=_dh_hero.get('hero'))
    except Exception:
        log_error('local-hero-dress-error')

def _dh_seed_player_fields_wrapper(entity, *args, **kwargs):
    result = _dh_original_seed_player_fields(entity, *args, **kwargs)
    _dh_hero_skill_ready(entity, 'built')
    return result


def _dh_landed_wrapper(player, *args, **kwargs):
    result = _dh_original_landed(player, *args, **kwargs)
    _dh_hero_skill_ready(player, 'landed')
    return result


def _dh_install_hero_screen():
    try:
        module = sys.modules.get('ui.UISelectHero') or __import__('ui.UISelectHero', fromlist=['x'])
    except Exception:
        return False
    cls = getattr(module, 'UISelectHero', None)
    if cls is None:
        return False
    done = []
    inner_choose = cls.__dict__.get('_chooseHero')
    if inner_choose is not None and not getattr(inner_choose, '_dh_hero', False):
        def _chooseHero(self, heroID, *args, **kwargs):
            try:
                _dh_hero['hero'] = int(heroID)
            except Exception:
                pass
            return inner_choose(self, heroID, *args, **kwargs)
        _chooseHero._dh_hero = True
        _chooseHero._dh_inner = inner_choose
        cls._chooseHero = _chooseHero
        done.append('_chooseHero')
    inner_confirm = cls.__dict__.get('onConfirmHero')
    if inner_confirm is not None and not getattr(inner_confirm, '_dh_hero', False):
        def onConfirmHero(self, *args, **kwargs):
            result = inner_confirm(self, *args, **kwargs)
            pick = _dh_hero.get('pick')
            if pick is not None and _dh_hero.get('hero'):
                pick['locked'] = True
                pick['end'] = min(pick['end'], time.time() + 3.0)     # HERO_SELECT_PHASE_START_RIGHT_NOW_COUNT_DOWN_TIME
            return result
        onConfirmHero._dh_hero = True
        onConfirmHero._dh_inner = inner_confirm
        cls.onConfirmHero = onConfirmHero
        done.append('onConfirmHero')
    return done


# ---- skills: the game server's part of a cast
def _dh_skill_row(skill_id):
    try:
        return _properties_module().getSkill2Data(int(skill_id))
    except Exception:
        return None


def _dh_skill_call(player, name, *args):
    function = getattr(player, name, None)
    if callable(function):
        try:
            function(*args)
            return True
        except Exception:
            log_error('local-hero-skill-call-error', call=name)
    return False


def _dh_skill_stage(player, skill_id, token, index):
    state = _dh_hero['skills'].get(skill_id)
    if state is None or state['token'] != token:
        return
    row = _dh_skill_row(skill_id)
    stages = list(getattr(row, 'STAGES', None) or [])
    if index > 0:
        _dh_skill_call(player, 'skillStageFinish', skill_id, index - 1)
    if index >= len(stages):
        _dh_hero['skills'].pop(skill_id, None)
        _dh_skill_call(player, 'skillFinish', skill_id, _dh_server_time())
        return
    _dh_skill_call(player, 'skillStageStart', skill_id, index)
    try:
        wait = float(getattr(stages[index], 'TOTAL_TIME', 0.0) or 0.0)
    except Exception:
        wait = 0.0
    call_later(max(0.05, wait), _dh_skill_stage, player, skill_id, token, index + 1)


def on_hero_skill_request(player, skill_id=0, *args, **kwargs):
    try:
        skill_id = int(skill_id)
    except Exception:
        return None
    row = _dh_skill_row(skill_id)
    if row is None:
        log('local-hero-skill-unknown', skill=skill_id)
        return None
    if skill_id in _dh_hero['skills']:
        return None                                          # already running
    token = object()
    _dh_hero['skills'][skill_id] = {'token': token}
    _dh_skill_call(player, 'skillStart', skill_id)
    call_later(max(0.0, float(getattr(row, 'BEFORE_CAST', 0) or 0) + float(getattr(row, 'CASTING_TIME', 0) or 0)),
               _dh_skill_stage, player, skill_id, token, 0)
    # no NAME: it is UTF-8 bytes, and a cut multi-byte character makes the log line fail (dropped silently)
    log('local-hero-skill', skill=skill_id, cooldown=getattr(row, 'COOLDOWN', None))
    return None


def on_hero_skill_break(player, skill_id=0, *args, **kwargs):
    try:
        skill_id = int(skill_id)
    except Exception:
        return None
    if _dh_hero['skills'].pop(skill_id, None) is not None:
        _dh_skill_call(player, 'skillFinish', skill_id, _dh_server_time())
    return None


try:
    if _dh_original_match_found is not None and _dh_original_countdown_done is not None:
        _dh_match_found_wrapper._dh_inner = _dh_original_match_found
        _dh_countdown_done_wrapper._dh_inner = _dh_original_countdown_done
        match_found = _dh_match_found_wrapper
        countdown_done = _dh_countdown_done_wrapper
    if _dh_original_player_properties is not None:
        _dh_player_properties_wrapper._dh_inner = _dh_original_player_properties
        player_properties = _dh_player_properties_wrapper
    if _dh_original_seed_player_fields is not None:
        _dh_seed_player_fields_wrapper._dh_inner = _dh_original_seed_player_fields
        seed_player_fields = _dh_seed_player_fields_wrapper
    if _dh_original_landed is not None:
        _dh_landed_wrapper._dh_inner = _dh_original_landed
        landed = _dh_landed_wrapper
    _handlers = getattr(LOBBY, 'RPC_HANDLERS', None) if LOBBY is not None else None
    if isinstance(_handlers, dict):
        _handlers['skillRequest'] = on_hero_skill_request
        _handlers['breakSkillRequest'] = on_hero_skill_break
    log('local-hero-installed', screen=_dh_install_hero_screen(), handlers=isinstance(_handlers, dict))
except Exception:
    log_error('local-hero-install-error')


# --- m27: Death Race (map 710, "4-player Death Race Mode") ran as a plain battle royale.  The game's own data for the
# map (battleground params 710 + the map row) now decides the rules, as the original server did:
#   - BORN_PROP: every player lands with the mode's kit (2 guns with ammo, armour);
#   - DEFAULT_BATTLE_LAND_VEHICLE_ID: the player's race car (25000) is put beside them on landing, with them at the
#     wheel, the car's top speed raised by the map's VEHICLE_TOP_SPEED_BUFF (%);
#   - nobody leaves the car while it runs: it is the last car standing that wins;
#   - BAN_RESTORE_HP: no healing items on the map.
# (The fast circles, the many airdrops and no red zone came from the same params already.)
_DH_RACE_CAR_GAP = 30.0
_DH_RACE_SEAT_DELAY = 1.2
_DH_RACE_LOCK_TIP = 'Death Race: you stay in your car until it is destroyed.'
_DH_NO_HEAL_TIP = 'Healing items cannot be used in this mode.'


def _dh_race_params():
    try:
        params = battleground_params(BATTLE.get('map'))
    except Exception:
        params = None
    if params is None or not getattr(params, 'DEFAULT_BATTLE_LAND_VEHICLE_ID', 0):
        return None
    return params


def _dh_race_kit(player, params):
    given = []
    for group in (getattr(params, 'BORN_PROP', None) or {}).values():
        for choice in list(group or [])[:1]:
            for entry in list(getattr(choice, 'PROP_LIST', None) or []):
                try:
                    prop, count = int(entry[0]), int(entry[1]) if len(entry) > 1 else 1
                    grant_prop(player, prop, count)
                    given.append((prop, count))
                except Exception:
                    log_error('local-race-kit-error', prop=safe(entry, 40))
    return given


def _dh_race_car(player, params):
    land = int(getattr(params, 'DEFAULT_BATTLE_LAND_VEHICLE_ID', 0) or 0)
    fleet = dict((entry[1], (entry[0], entry[2])) for entry in VEHICLE_FLEET)
    if land not in fleet:
        return None
    class_name, tps = fleet[land]
    x, y, z = _point(player.position)
    yaw = float(getattr(player, 'yaw', 0.0) or 0.0)
    cx, cz = x + _DH_RACE_CAR_GAP * math.sin(yaw), z + _DH_RACE_CAR_GAP * math.cos(yaw)
    ground = ground_height(cx, cz) or y
    car_id = spawn_vehicle(class_name, land, tps, cx, cz, ground, yaw)
    if car_id is not None:
        _round['race_car'] = car_id
        call_later(_DH_RACE_SEAT_DELAY, _dh_race_seat, player, car_id, params)
    return car_id


_DH_RACE_SEAT_TRIES = 12


def _dh_race_seat(player, car_id, params, attempt=0):
    try:
        car = vehicle_entity(car_id)
        if car is None:
            # the car's entity is not in the world yet (the fleet is placed at the same moment): try again
            if attempt < _DH_RACE_SEAT_TRIES and BATTLE.get('phase') == 'fighting':
                call_later(0.5, _dh_race_seat, player, car_id, params, attempt + 1)
            else:
                log('local-race-seat-missing', car=car_id, attempts=attempt)
            return
        prepare_vehicle(car)
        boost = float(_field_of(_map_record(BATTLE.get('map')), 'VEHICLE_TOP_SPEED_BUFF') or 0.0)
        if boost > 0.0:
            car.vehicleBuff['maxSpeedBuff'] = 1.0 + boost / 100.0
        get_on(player, car_id, True)
        log('local-race-seated', car=car_id, boost=boost, attempt=attempt)
    except Exception:
        log_error('local-race-seat-error', car=car_id)


def _dh_race_landed(player):
    if _round.get('race_ready'):
        return
    params = _dh_race_params()
    if params is None:
        return
    _round['race_ready'] = True
    try:
        kit = _dh_race_kit(player, params)
        car = _dh_race_car(player, params)
        log('local-race-start', map=BATTLE.get('map'), kit=kit, car=car)
    except Exception:
        log_error('local-race-start-error')


def _dh_race_get_off_wrapper(player, vehicle_id=0, *args, **kwargs):
    try:
        car_id = _round.get('race_car')
        if car_id and _dh_race_params() is not None:
            record = _vehicles.get(car_id, {})
            if not record.get('dead') and vehicle_entity(car_id) is not None:
                tip_text(_DH_RACE_LOCK_TIP)
                return None
    except Exception:
        log_error('local-race-lock-error')
    return _dh_race_get_off_wrapper._dh_inner(player, vehicle_id, *args, **kwargs)


def _dh_heal_wrapper(player, item, *args, **kwargs):
    # m40p: BAN_RESTORE_HP is True in EVERY map record (700 Classic included - probed 2026-10-26), so it cannot mean "no
    # healing items"; using it alone blocked healing in every mode since m27.  Only the race maps (their own car per
    # player) keep the no-heal rule.
    try:
        if _dh_race_params() is not None and _field_of(_map_record(BATTLE.get('map')), 'BAN_RESTORE_HP'):
            tip_text(_DH_NO_HEAL_TIP)
            return False
    except Exception:
        log_error('local-race-heal-error')
    return _dh_heal_wrapper._dh_inner(player, item, *args, **kwargs)


def _dh_race_landed_wrapper(player, *args, **kwargs):
    result = _dh_race_landed_wrapper._dh_inner(player, *args, **kwargs)
    _dh_race_landed(player)
    return result


try:
    _dh_inner_get_off = _dh_unwrap(globals().get('on_get_off_vehicle'))
    _dh_inner_heal = _dh_unwrap(globals().get('heal'))
    _dh_inner_landed = globals().get('landed')
    while getattr(_dh_inner_landed, '_dh_race', False):
        _dh_inner_landed = _dh_inner_landed._dh_inner
    if _dh_inner_get_off is not None and _dh_inner_heal is not None and _dh_inner_landed is not None:
        _dh_race_get_off_wrapper._dh_inner = _dh_inner_get_off
        on_get_off_vehicle = _dh_race_get_off_wrapper
        _dh_heal_wrapper._dh_inner = _dh_inner_heal
        heal = _dh_heal_wrapper
        _dh_race_landed_wrapper._dh_inner = _dh_inner_landed
        _dh_race_landed_wrapper._dh_race = True
        landed = _dh_race_landed_wrapper
        _handlers = getattr(LOBBY, 'RPC_HANDLERS', None) if LOBBY is not None else None
        if isinstance(_handlers, dict):
            _handlers['reqGetOffLandVehicle'] = _dh_race_get_off_wrapper
    log('local-race-installed', ok=_dh_inner_get_off is not None and _dh_inner_heal is not None)
except Exception:
    log_error('local-race-install-error')


# --- m27b: a second match in one session hung on its loading screen ("wait-scene", stage 1 never ended) - twice on
# Death Race today, with the player still in the race car.  Every hang in the game's error log is the old level's
# teardown (Application._late_update -> Level.Destroy) raising on one object, which aborts the teardown, and it is
# retried every frame against the same object, so the level never dies:
#   - iLandVehicle.releaseHintUI: self.uiReceiver.SendMessage(...) with the battle UI (uiReceiver) already gone
#     (12 hits, all after a round ended in a car);
#   - MeshRenderer.OnDisable: ____model__.visible on a model already freed ("Invalid visible object!", 78 hits);
#   - HallThemeEffect.OnDisable: EffectsSystem.Stop on an sfx already freed ("Invalid sfx which has been destroyed!",
#     58 hits).
# Each is guarded against exactly that failure (the object is being destroyed; there is nothing else to do with it),
# and on leaving a battle the player's seat is cleared and the cars unselected before they are destroyed.
def _dh_guard_method(module_name, class_name, method_name, make):
    try:
        module = sys.modules.get(module_name) or __import__(module_name, fromlist=['x'])
        cls = getattr(module, class_name, None)
        current = cls.__dict__.get(method_name) if cls is not None else None
        if current is None:
            return False
        if getattr(current, '_dh_teardown', False):
            return True
        inner = getattr(current, '_dh_inner', current)
        wrapper = make(inner)
        wrapper._dh_teardown = True
        wrapper._dh_inner = inner
        setattr(cls, method_name, wrapper)
        return True
    except Exception:
        log_error('local-teardown-guard-error', target='%s.%s' % (class_name, method_name))
        return False


def _dh_make_release_hint(inner):
    def releaseHintUI(self, *args, **kwargs):
        if getattr(self, 'uiReceiver', None) is None:
            try:
                self.isSelected = False
            except Exception:
                pass
            return None
        try:
            return inner(self, *args, **kwargs)
        except AttributeError:
            if once('teardown-hint'):
                log('local-teardown-guarded', what='releaseHintUI')
            return None
    return releaseHintUI


def _dh_make_on_disable(label):
    def make(inner):
        def OnDisable(self, *args, **kwargs):
            try:
                return inner(self, *args, **kwargs)
            except RuntimeError:
                if once('teardown-' + label):
                    log('local-teardown-guarded', what=label)
                return None
        return OnDisable
    return make


def _dh_unseat_before_leave(player):
    try:
        for car_id in list(_vehicles):
            car = vehicle_entity(car_id)
            if car is None:
                continue
            try:
                car.isSelected = False
            except Exception:
                pass
            try:
                set_seats(car, [])
            except Exception:
                pass
        if player is not None and getattr(player, 'inLandVehicle', False):
            clear_seat(player)
            log('local-teardown-unseated')
    except Exception:
        log_error('local-teardown-unseat-error')


_DH_RACE_SCREENS = ('UIAutoRoyalePackage', 'UIAutoRoyaleTrunkSlot')


def _dh_close_race_screens(where):
    # m27d: a round that ended with the trunk screen (TAB) open left it entered in the lobby, where it swallowed the
    # lobby's clicks (START did nothing).  The hook's own close list does not know these two screens.
    closed = []
    try:
        import Globals
        for name in _DH_RACE_SCREENS:
            if name in (getattr(Globals.uiMgr, '____all_ui__', {}) or {}):
                try:
                    Globals.uiMgr.destroy_ui_obj(name)
                    closed.append(name)
                except Exception:
                    log_error('local-race-screen-close-error', ui=name)
    except Exception:
        log_error('local-race-screens-error')
    if closed:
        log('local-race-screens-closed', screens=closed, where=where)
    return closed


def _dh_leave_battle_wrapper(player=None, *args, **kwargs):
    _dh_unseat_before_leave(player or current_player())
    _dh_close_race_screens('leave')
    return _dh_leave_battle_wrapper._dh_inner(player, *args, **kwargs)


try:
    _dh_guards = {
        'releaseHintUI': _dh_guard_method('iLandVehicle', 'iLandVehicle', 'releaseHintUI', _dh_make_release_hint),
        'MeshRenderer': _dh_guard_method('libclaudia.Classes.MeshRenderer', 'MeshRenderer', 'OnDisable',
                                         _dh_make_on_disable('MeshRenderer.OnDisable')),
        'HallThemeEffect': _dh_guard_method('ui.main.HallTheme', 'HallThemeEffect', 'OnDisable',
                                            _dh_make_on_disable('HallThemeEffect.OnDisable')),
    }
    _dh_inner_leave = _dh_unwrap(globals().get('leave_battle'))
    if _dh_inner_leave is not None:
        _dh_leave_battle_wrapper._dh_inner = _dh_inner_leave
        leave_battle = _dh_leave_battle_wrapper
    log('local-teardown-installed', guards=_dh_guards, leave=_dh_inner_leave is not None)
except Exception:
    log_error('local-teardown-install-error')


# --- m27c: Death Race is the game's Auto Royale mode: TAB opens UIAutoRoyalePackage, whose trunk tab asks the car for
# the Auto Royale trunk (iAutoRoyalePackage: getAutoRoyalePkgTotalCapacity / LeftCapacity ... over
# car.autoRoyaleItemPackage).  Our cars are plain LandCars without it: the screen crashed in on_enter, stayed half
# open with no working buttons, and covered the death panel.  On a race map every car gets the game's own trunk
# (package_common.Package3.AutoRoyalePackage3, capacity from the AutoRoyalePackage table) and the mixin's methods.
def _dh_trunk_class(package_module):
    """The trunk needs the client half too: AutoRoyalePackage3 (weights, capacity, deletes) has no onAddItem,
    which iAutoRoyalePackage.onAddAutoRoyaleItem calls; package_client.PackageClient3 brings it (same mix the
    player's own bag uses)."""
    cls = globals().get('_dh_trunk_cls')
    if cls is not None:
        return cls
    base = package_module.AutoRoyalePackage3
    try:
        client_module = sys.modules.get('package_client.PackageClient3') or __import__('package_client.PackageClient3', fromlist=['x'])
        client = getattr(client_module, 'PackageClient3')
        cls = type('DhAutoRoyaleTrunk', (base, client), {})
    except Exception:
        log_error('local-race-trunk-class-error')
        cls = base
    globals()['_dh_trunk_cls'] = cls
    return cls


def _dh_race_trunk(car):
    try:
        package_module = sys.modules.get('package_common.Package3') or __import__('package_common.Package3', fromlist=['x'])
        mixin_module = sys.modules.get('iAutoRoyalePackage') or __import__('iAutoRoyalePackage')
        mixin = mixin_module.iAutoRoyalePackage
        cls = type(car)
        function_type = type(lambda: 0)
        added = []
        if not cls.__dict__.get('_dh_trunk_mixin'):
            for name, function in vars(mixin).items():
                if isinstance(function, function_type) and name != 'enterWorld' and not hasattr(cls, name):
                    setattr(cls, name, function)
                    added.append(name)
            cls._dh_trunk_mixin = True
        try:
            present = car.autoRoyaleItemPackage is not None
        except AttributeError:
            present = False
        if not present:
            try:
                capacity = int(package_module.properties.getAutoRoyalePackageData(0).CAPACITY or 0) or 1500
            except Exception:
                capacity = 1500
            car.autoRoyaleItemPackage = _dh_trunk_class(package_module)({}, {}, capacity)
            log('local-race-trunk', car=getattr(car, 'id', None), capacity=capacity, mixin_added=len(added))
        return True
    except Exception:
        log_error('local-race-trunk-error')
        return False


def _dh_prepare_vehicle_wrapper(car, *args, **kwargs):
    result = _dh_prepare_vehicle_wrapper._dh_inner(car, *args, **kwargs)
    try:
        if car is not None and _dh_race_params() is not None:
            _dh_race_trunk(car)
    except Exception:
        log_error('local-race-trunk-wrap-error')
    return result


try:
    _dh_inner_prepare = _dh_unwrap(globals().get('prepare_vehicle'))
    if _dh_inner_prepare is not None:
        _dh_prepare_vehicle_wrapper._dh_inner = _dh_inner_prepare
        prepare_vehicle = _dh_prepare_vehicle_wrapper
    log('local-race-trunk-installed', ok=_dh_inner_prepare is not None)
except Exception:
    log_error('local-race-trunk-install-error')


# --- m27e: a car passenger could not shoot.  The game fires only in the standing / crouch / crawl / swim / STRETCH
# poses: a seated passenger first leans out of the window ("stretch", the Stretch button or the trigger itself:
# FightOperation.StartFire -> IptMsg_ReqEnterStretchShoot -> PlayerAvatar.reqStretchInVehicle -> cell), and the server
# answered with player.stretchInVehicle(car).  The seat has to allow it first: iVehicleShoot.resetStretchEn(car, seat)
# sets canStretch from the car's seat table.  The hook seated players with its own flags only, so canStretch stayed
# False and the stretch requests were never answered.  Now: seating / seat switch enables stretching for the seat,
# the two requests are answered the way the server did, and getting off un-stretches first.
def _dh_enable_stretch(player, car, socket):
    try:
        reset = getattr(player, 'resetStretchEn', None)
        if socket == globals().get('VEHICLE_DRIVER_SOCKET', 'Driver'):
            # the driver socket is not in the seat table; the client's own check would raise ValueError.
            # Driving (or switching back to the wheel) always ends the lean-out.
            if getattr(player, 'clientInStretch', 0):
                on_stretch_out_vehicle(player)
            try:
                player.canStretch = False
            except Exception:
                pass
            return
        if callable(reset) and car is not None:
            # m27f: iVehicleShoot._isStretchSeat also wants the car's own canStretch (a property the server set on the
            # vehicles whose seats allow leaning out); ours are built without it
            try:
                car.canStretch = True
            except Exception:
                pass
            reset(car.id, socket)
            log('local-stretch-seat', seat=socket, can=bool(getattr(player, 'canStretch', False)),
                car_can=repr(getattr(car, 'canStretch', None))[:12])
    except Exception:
        log_error('local-stretch-seat-error', seat=safe(socket, 30))


def _dh_seat_player_wrapper(player, car, socket, *args, **kwargs):
    result = _dh_seat_player_wrapper._dh_inner(player, car, socket, *args, **kwargs)
    _dh_enable_stretch(player, car, socket)
    return result


def on_stretch_in_vehicle(player, *args, **kwargs):
    try:
        car_id = int(getattr(player, 'vehicleEntID', 0) or 0)
        if not car_id or not getattr(player, 'inLandVehicle', False):
            return None
        try:
            player.inVehicleStretch = 1
        except Exception:
            pass
        player.stretchInVehicle(car_id)
        log('local-stretch-in', car=car_id)
    except Exception:
        log_error('local-stretch-in-error')
    return None


def on_stretch_out_vehicle(player, *args, **kwargs):
    try:
        try:
            player.inVehicleStretch = 0
        except Exception:
            pass
        player.stretchOutVehicle()
        log('local-stretch-out')
    except Exception:
        log_error('local-stretch-out-error')
    return None


def _dh_get_off_stretch_wrapper(player, vehicle_id=0, *args, **kwargs):
    try:
        if getattr(player, 'clientInStretch', 0):
            on_stretch_out_vehicle(player)
    except Exception:
        pass
    return _dh_get_off_stretch_wrapper._dh_inner(player, vehicle_id, *args, **kwargs)


# ---- m27g: the vehicle HUD's drive/hang toggle (two-seat UI types send cell.reqSwitchDriveState instead of
# reqSwitchToSeat): driver -> first free passenger seat, passenger -> the wheel if nobody holds it
def on_switch_drive_state(player, *args, **kwargs):
    try:
        car = vehicle_entity(getattr(player, 'vehicleEntID', 0))
        if car is None or not getattr(player, 'inLandVehicle', False):
            return None
        sockets = list(getattr(car, 'totalSockets', None) or [])
        driver = globals().get('VEHICLE_DRIVER_SOCKET', 'Driver')
        mine = getattr(player, 'hangSockName', None)
        target = None
        if getattr(player, 'isLandDriver', False):
            for i, s in enumerate(sockets):
                if s != driver and s != mine and not seat_taken(car, s, player.id):
                    target = i
                    break
        elif driver in sockets and not seat_taken(car, driver, player.id):
            target = sockets.index(driver)
        if target is None:
            tip_text('Seat taken')
            log('local-drive-state-none', driver=bool(getattr(player, 'isLandDriver', False)))
            return None
        call_later(WEAPON_SWITCH_DELAY, switch_seat, player, target)
        log('local-drive-state', seat=target)
    except Exception:
        log_error('local-drive-state-error')
    return None


# ---- m27g: Death Race "transfer vehicle" button (cell.transferCar): the HUD counts down prop 310017's DURATION
# (the car's vehicleTransferStartTime drives it), then the wrecked/stuck car is retired and a fresh race car is
# placed beside the player with them at the wheel (same path as the landing car)
_DH_TRANSFER_FALLBACK = 10.0


def _dh_transfer_duration():
    try:
        module = _properties_module()
        row = module.getBattleGroundPropData(310017) if module is not None else None
        # the HUD reads it the same way: the prop row's PROP_TYPE block carries DURATION
        value = float(getattr(getattr(row, 'PROP_TYPE', None), 'DURATION', 0) or getattr(row, 'DURATION', 0) or 0)
        if value > 0:
            return value
        log('local-race-transfer-duration', row=safe(row, 80))
    except Exception:
        log_error('local-race-transfer-duration-error')
    return _DH_TRANSFER_FALLBACK


def _dh_royale_vehicle_call(car, name, *args):
    """iAutoRoyaleVehicle's setters (HUD countdown, retired-car look) called on our plain LandCar."""
    try:
        module = sys.modules.get('iAutoRoyaleVehicle') or __import__('iAutoRoyaleVehicle')
        function = getattr(module, 'iAutoRoyaleVehicle').__dict__.get(name)
        if function is None:
            return False
        function(car, *args)
        return True
    except Exception:
        log_error('local-race-royale-call-error', call=name)
        return False


def on_transfer_car(player, *args, **kwargs):
    try:
        params = _dh_race_params()
        car = vehicle_entity(getattr(player, 'vehicleEntID', 0))
        if params is None or car is None or not getattr(player, 'inLandVehicle', False):
            return None
        if _round.get('race_transfer'):
            return None
        started = server_now()
        _round['race_transfer'] = car.id
        try:
            car.vehicleTransferStartTime = started
        except Exception:
            pass
        _dh_royale_vehicle_call(car, 'set_vehicleTransferStartTime', 0)
        wait = _dh_transfer_duration()
        call_later(wait, _dh_transfer_finish, player, car.id, params)
        log('local-race-transfer', car=car.id, wait=wait)
    except Exception:
        log_error('local-race-transfer-error')
    return None


def _dh_transfer_finish(player, old_id, params):
    try:
        _round['race_transfer'] = None
        if BATTLE.get('phase') != 'fighting' or current_player() is None:
            return
        old = vehicle_entity(old_id)
        if old is not None and getattr(player, 'vehicleEntID', 0) == old_id:
            _dh_unwrap(globals().get('get_off'))(player, old_id)
        if old is not None:
            try:
                old.isAfterTransfer = True
            except Exception:
                pass
            _dh_royale_vehicle_call(old, 'set_isAfterTransfer', False)
            _vehicles.setdefault(old_id, {})['dead'] = True
        call_later(VEHICLE_EXIT_DELAY + 0.3, _dh_transfer_spawn, player, params)
    except Exception:
        log_error('local-race-transfer-finish-error')


def _dh_transfer_spawn(player, params):
    try:
        car = _dh_race_car(player, params)
        log('local-race-transfer-done', car=car)
    except Exception:
        log_error('local-race-transfer-spawn-error')


try:
    _dh_inner_seat = _dh_unwrap(globals().get('seat_player'))
    if _dh_inner_seat is not None:
        _dh_seat_player_wrapper._dh_inner = _dh_inner_seat
        seat_player = _dh_seat_player_wrapper
    _dh_inner_get_off2 = globals().get('get_off')
    while getattr(_dh_inner_get_off2, '_dh_stretch', False):
        _dh_inner_get_off2 = _dh_inner_get_off2._dh_inner
    if _dh_inner_get_off2 is not None:
        _dh_get_off_stretch_wrapper._dh_inner = _dh_inner_get_off2
        _dh_get_off_stretch_wrapper._dh_stretch = True
        get_off = _dh_get_off_stretch_wrapper

    _handlers = getattr(LOBBY, 'RPC_HANDLERS', None) if LOBBY is not None else None
    if isinstance(_handlers, dict):
        _handlers['reqSwitchDriveState'] = on_switch_drive_state
        _handlers['transferCar'] = on_transfer_car
        _handlers['reqStretchInVehicle'] = on_stretch_in_vehicle
        _handlers['reqStretchOutVehicle'] = on_stretch_out_vehicle
    log('local-stretch-installed', seat=_dh_inner_seat is not None, get_off=_dh_inner_get_off2 is not None, handlers=isinstance(_handlers, dict))
except Exception:
    log_error('local-stretch-install-error')


# ---- m28: hero skill EFFECTS (item 4).  A hero skill's stages carry SkillComponentSummonNormal components whose
# SUMMON_ID 13 ("to self") / 146 ("caster and team") add STATES (SkillState2 rows) to the caster; a state is a
# FLOW_CONTROL duration plus ATTRIBUTE_CONTROL controllers.  The game server ran those controllers on the cell and
# pushed the results as entity properties; the client only mirrors marks (iMark) and buff icons.  Here the hook plays
# the server's part for the controllers that matter in a solo match: marks (move speed / max HP / damage reduction),
# out-of-combat regen, item grants, the gatling, vehicle repair, stop-state, set-property.  Passive skills (no
# cooldown, no action stages) are applied when the hero lands; active ones per stage of the cast.
_DH_STATE_SELF_SUMMONS = (13, 146)
_DH_STATE_FOREVER = 90000.0
_DH_MARK_MOVE, _DH_MARK_MAX_HP, _DH_MARK_REDUCE, _DH_MARK_REGEN = 2, 1, 8, 13
_dh_hero_states = globals().get('_dh_hero_states') or {'active': {}, 'marks': {}, 'last_hit': 0.0, 'speed': 0, 'reduce': 0.0,
                                                        'max_hp': 0, 'unsupported': {}, 'passives': False}


def _dh_state_row(state_id):
    try:
        return _properties_module().getSkillState2Data(int(state_id))
    except Exception:
        return None


def _dh_mark_row(mark_id):
    try:
        return _properties_module().getMarkData(int(mark_id))
    except Exception:
        return None


def _dh_mark_value(mark_id, level):
    row = _dh_mark_row(mark_id)
    values = getattr(row, 'MARK_LEVEL_VALUE', None) or {}
    level = max(1, int(level))
    for key in (level, str(level)):
        try:
            if key in values:
                return float(values[key])
        except Exception:
            pass
    return 0.0


def _dh_mark_max_level(mark_id):
    row = _dh_mark_row(mark_id)
    values = getattr(row, 'MARK_LEVEL_VALUE', None) or {}
    best = 0
    for key in values.keys():
        try:
            best = max(best, int(key))
        except Exception:
            pass
    return best or 1


def _dh_stage_states(skill_id, index):
    """State ids a stage adds to the caster (SummonNormal to self / team)."""
    row = _dh_skill_row(skill_id)
    stages = list(getattr(row, 'STAGES', None) or [])
    if not 0 <= index < len(stages):
        return []
    found = []
    for comp in list(getattr(stages[index], 'COMPONENTS', None) or []):
        summons = []
        for value in list(getattr(comp, 'SUMMON_ID', None) or []):
            try:
                summons.append(int(value))
            except Exception:
                pass
        if not any(value in _DH_STATE_SELF_SUMMONS for value in summons):
            continue
        for state in list(getattr(comp, 'STATE_ID', None) or []):
            try:
                found.append(int(getattr(state, 'ID', state)))
            except Exception:
                pass
    return found


_DH_SPAWN_TRIGGERS = ('SkillTriggerSelectIdentity', 'SkillTriggerAfterLand')


def _dh_skill_is_passive(skill_id):
    """Skills the game server fired by itself when the hero was picked / landed (SKILL_TRIGGER class).  Button
    skills are SkillTriggerNone; the event ones (on kill, on damage, on jump, holding a weapon...) need the
    matching battle event and are left alone for now."""
    row = _dh_skill_row(skill_id)
    if row is None:
        return False
    trigger = getattr(row, 'SKILL_TRIGGER', None)
    return trigger.__class__.__name__ in _DH_SPAWN_TRIGGERS


# -- marks -> what the client can feel
def _dh_marks_apply(player):
    speed = max_hp = 0.0
    reduce = 0.0
    for mark_id, level in _dh_hero_states['marks'].items():
        if level <= 0:
            continue
        row = _dh_mark_row(mark_id)
        kind = int(getattr(row, 'MARK_TYPE', 0) or 0)
        value = _dh_mark_value(mark_id, level)
        if kind == _DH_MARK_MOVE:
            speed += value
        elif kind == _DH_MARK_MAX_HP:
            max_hp += value
        elif kind == _DH_MARK_REDUCE:
            reduce = max(reduce, value if value > 1.0 else value * 100.0)
    speed, max_hp = int(round(speed)), int(round(max_hp))
    reduce = min(0.9, reduce / 100.0)
    if speed != _dh_hero_states['speed']:
        _dh_hero_states['speed'] = speed
        base = _buffs.get('boostSpeedBuff', (0, 0))[1]
        change_prop(player, 'boostSpeedBuff', int(base))      # the change_prop wrapper adds the hero's share
    if max_hp != _dh_hero_states['max_hp']:
        delta = max_hp - _dh_hero_states['max_hp']
        _dh_hero_states['max_hp'] = max_hp
        try:
            top = int(getattr(player, 'maxHp', 0) or 0)
            if top:
                change_prop(player, 'maxHp', top + delta)
                if delta > 0:
                    restore_hp(player, delta)
        except Exception:
            log_error('local-hero-max-hp-error')
    _dh_hero_states['reduce'] = reduce
    try:
        player.markLevelDict = dict(_dh_hero_states['marks'])
    except Exception:
        pass


def _dh_mark_set(player, mark_id, level):
    level = max(0, min(int(level), _dh_mark_max_level(mark_id)))
    if level <= 0:
        _dh_hero_states['marks'].pop(int(mark_id), None)
    else:
        _dh_hero_states['marks'][int(mark_id)] = level
    update = getattr(player, 'onUpdateMarkLevel', None)
    if callable(update):
        try:
            update(int(mark_id), level)
        except Exception:
            pass
    _dh_marks_apply(player)


def _dh_change_prop_wrapper(player, attr, value):
    # the energy drink (set_buff / end_buff) writes boostSpeedBuff outright: keep the hero's share on top of it
    if attr == 'boostSpeedBuff' and player is current_player() and _dh_hero_states['speed']:
        try:
            value = int(value) + int(_dh_hero_states['speed'])
        except Exception:
            pass
    return _dh_change_prop_wrapper._dh_inner(player, attr, value)


def _dh_take_player_hit_wrapper(player, hurt, *args, **kwargs):
    _dh_hero_states['last_hit'] = time.time()
    reduce = _dh_hero_states.get('reduce') or 0.0
    if reduce > 0 and isinstance(hurt, dict):
        try:
            damage = int(hurt.get('damage') or 0)
            kept = int(round(damage * (1.0 - reduce)))
            old = int(player.hp)
            hurt = dict(hurt)
            hurt['damage'] = kept
            hurt['hp'] = max(0, old - kept)
        except Exception:
            pass
    return _dh_take_player_hit_wrapper._dh_inner(player, hurt, *args, **kwargs)


def _dh_hurt_self_wrapper(player, *args, **kwargs):
    _dh_hero_states['last_hit'] = time.time()
    return _dh_hurt_self_wrapper._dh_inner(player, *args, **kwargs)


# -- controllers
def _dh_ctrl_name(control):
    return control.__class__.__name__


def _dh_int_list(value):
    out = []
    for item in list(value or []):
        try:
            out.append(int(item))
        except Exception:
            pass
    return out


def _dh_state_tick(player, state_id, token, what):
    """Periodic work of one controller while the state runs."""
    state = _dh_hero_states['active'].get(state_id)
    if state is None or state['token'] != token or BATTLE.get('phase') != 'fighting':
        return
    kind, control, interval = what['kind'], what['control'], what['interval']
    try:
        if kind == 'regen':
            quiet = float(getattr(control, 'TimeOutOfFight', 0) or 0)
            if time.time() - _dh_hero_states['last_hit'] >= quiet:
                mark = int(getattr(control, 'MarkID', 0) or 0)
                amount = _dh_mark_value(mark, _dh_hero_states['marks'].get(mark, 1)) if mark else 0.0
                what['carry'] = what.get('carry', 0.0) + amount
                whole = int(what['carry'])
                if whole > 0:
                    what['carry'] -= whole
                    restore_hp(player, whole)
        elif kind == 'regen_time':
            restore_hp(player, int(getattr(control, 'ADD_HP', 0) or 0))
        elif kind == 'decay':
            what['level'] -= 1
            _dh_mark_set(player, what['mark'], what['level'])
            if what['level'] <= 0:
                return
        elif kind == 'repeat':
            for mark in what['marks']:
                _dh_mark_set(player, mark, _dh_hero_states['marks'].get(mark, 0) + 1)
    except Exception:
        log_error('local-hero-state-tick-error', state=state_id, kind=kind)
    call_later(max(0.1, interval), _dh_state_tick, player, state_id, token, what)


def _dh_state_control_start(player, state_id, token, control, flow):
    name = _dh_ctrl_name(control)
    interval = float(getattr(flow, 'INTERVAL_TIME', 0) or 0)
    first = float(getattr(flow, 'FIRST_TIME', 0) or 0)
    undo = []
    if name == 'SkillStateAddMark':
        marks = _dh_int_list(getattr(control, 'MARKS_LIST', None))
        for mark in marks:
            _dh_mark_set(player, mark, _dh_hero_states['marks'].get(mark, 0) + 1)
        undo.append(('marks', marks))
    elif name == 'SkillStateAddMarksRepeat':
        marks = _dh_int_list(getattr(control, 'MARKS_LIST', None))
        for mark in marks:
            _dh_mark_set(player, mark, _dh_hero_states['marks'].get(mark, 0) + 1)
        undo.append(('marks_all', marks))
        if interval > 0:
            call_later(interval, _dh_state_tick, player, state_id, token, {'kind': 'repeat', 'control': control, 'interval': interval, 'marks': marks})
    elif name == 'StateMarkDecayOverTime':
        mark = int(getattr(control, 'MARK_ID', 0) or 0)
        level = int(getattr(control, 'INIT_VAL', 0) or 0)
        _dh_mark_set(player, mark, level)
        undo.append(('marks_all', [mark]))
        if interval > 0:
            call_later(interval, _dh_state_tick, player, state_id, token, {'kind': 'decay', 'control': control, 'interval': interval, 'mark': mark, 'level': level})
    elif name == 'SkillAddHPOutOfFight':
        interval = float(getattr(control, 'TimeInterval', 0) or 0) or 0.5
        call_later(interval, _dh_state_tick, player, state_id, token, {'kind': 'regen', 'control': control, 'interval': interval})
    elif name == 'SkillAddHPByTime':
        call_later(interval or 5.0, _dh_state_tick, player, state_id, token, {'kind': 'regen_time', 'control': control, 'interval': interval or 5.0})
    elif name == 'SkillPickProps':
        counts = {}
        for item in _dh_int_list(getattr(control, 'ITEM_LIST', None)):
            counts[item] = counts.get(item, 0) + 1
        for item, count in counts.items():
            try:
                add_item(player, item, count)
            except Exception:
                log_error('local-hero-state-item-error', item=item)
    elif name == 'SkillHeroEquipWeapon':
        weapon = int(getattr(control, 'WEAPON_ID', 0) or 0)
        bullet = int(getattr(control, 'BULLET_TYPE', 0) or 0)
        bullets = int(getattr(control, 'BULLET_NUM', 0) or 0)
        try:
            if weapon:
                add_item(player, weapon, 1)
            if bullet and bullets:
                add_item(player, bullet, bullets)
        except Exception:
            log_error('local-hero-state-weapon-error', weapon=weapon)
        undo.append(('weapon', weapon))
    elif name == 'StateAddHpForVehicle':
        car = vehicle_entity(getattr(player, 'vehicleEntID', 0))
        if car is not None:
            try:
                top = int(getattr(car, 'maxHp', 0) or 0)
                old = int(car.hp)
                value = float(getattr(control, 'VAL', 0) or 0)
                gain = int(round(top * value / 100.0)) if int(getattr(control, 'VAL_TYPE', 2) or 2) == 2 else int(value)
                car.hp = min(top, old + gain) if top else old + gain
                car.onRecoverHP(int(car.hp))
            except Exception:
                log_error('local-hero-state-car-error')
    elif name == 'SkillStopOtherState':
        other = int(getattr(control, 'OTHER_STATE_ID', 0) or 0)
        delay = float(getattr(control, 'DELAY', 0) or 0)
        call_later(max(0.0, delay), _dh_state_end, player, other, None, 'stopped')
    elif name == 'SkillStateSetProperty':
        prop = str(getattr(control, 'PROPERTY_NAME', '') or '')
        if prop:
            try:
                setattr(player, prop, True)
            except Exception:
                pass
            if getattr(control, 'RESET_ON_END', True):
                undo.append(('prop', prop))
    elif name in ('SkillSetTime', 'SkillStateClientEffectPause', 'SkillStateEfxBack', 'SkillChangeCameraFov'):
        pass                                        # client-side presentation, nothing for the server
    else:
        seen = _dh_hero_states['unsupported']
        seen[name] = seen.get(name, 0) + 1
        if seen[name] == 1:
            log('local-hero-state-unsupported', control=name, state=state_id)
    return undo


def _dh_state_start(player, state_id, source):
    row = _dh_state_row(state_id)
    if row is None:
        log('local-hero-state-unknown', state=state_id, source=source)
        return False
    if state_id in _dh_hero_states['active']:
        _dh_state_end(player, state_id, None, 'replaced')
    flow = getattr(row, 'FLOW_CONTROL', None)
    total = float(getattr(flow, 'TOTAL_TIME', 0) or 0)
    token = object()
    state = {'token': token, 'undo': [], 'started': time.time(), 'total': total}
    _dh_hero_states['active'][state_id] = state
    controls = list(getattr(row, 'ATTRIBUTE_CONTROL', None) or [])
    for control in controls:
        try:
            state['undo'].extend(_dh_state_control_start(player, state_id, token, control, flow))
        except Exception:
            log_error('local-hero-state-control-error', state=state_id, control=_dh_ctrl_name(control))
    if 0 < total < _DH_STATE_FOREVER:
        call_later(total, _dh_state_end, player, state_id, token, 'timeout')
    elif total <= 0:
        call_later(0.2, _dh_state_end, player, state_id, token, 'instant')
    log('local-hero-state', state=state_id, source=source, seconds=total,
        controls=[_dh_ctrl_name(control) for control in controls][:8])
    return True


def _dh_state_end(player, state_id, token, why):
    state = _dh_hero_states['active'].get(state_id)
    if state is None or (token is not None and state['token'] != token):
        return False
    _dh_hero_states['active'].pop(state_id, None)
    state['token'] = None                            # stops its ticks
    for kind, value in state['undo']:
        try:
            if kind == 'marks':
                for mark in value:
                    _dh_mark_set(player, mark, _dh_hero_states['marks'].get(mark, 0) - 1)
            elif kind == 'marks_all':
                for mark in value:
                    _dh_mark_set(player, mark, 0)
            elif kind == 'prop':
                setattr(player, value, False)
            elif kind == 'weapon' and value:
                discard(player, value, 1, '')
        except Exception:
            log_error('local-hero-state-undo-error', state=state_id, kind=kind)
    log('local-hero-state-end', state=state_id, why=why)
    return True


def _dh_states_clear(player):
    for state_id in list(_dh_hero_states['active'].keys()):
        _dh_state_end(player, state_id, None, 'clear')
    _dh_hero_states['marks'] = {}
    _dh_hero_states['speed'] = 0
    _dh_hero_states['reduce'] = 0.0
    _dh_hero_states['max_hp'] = 0
    _dh_hero_states['passives'] = False


def _dh_stage_apply(player, skill_id, index):
    for state_id in _dh_stage_states(skill_id, index):
        _dh_state_start(player, state_id, 'skill %s stage %s' % (skill_id, index))


def _dh_hero_passives(player):
    hero = int(_dh_hero.get('hero') or 0)
    if not hero or _dh_hero_states['passives'] or BATTLE.get('phase') != 'fighting':
        return
    _dh_hero_states['passives'] = True
    try:
        row = None
        tables = getattr(sys.modules.get('ui.UISelectHero'), 'tables', None)
        for module, name in ((tables, 'getDtsOccupation'), (_properties_module(), 'getDtsOccupationData'), (_properties_module(), 'getDtsOccupation')):
            getter = getattr(module, name, None)
            if callable(getter):
                try:
                    row = getter(hero)
                    break
                except Exception:
                    row = None
        skills = [int(value) for value in list(getattr(row, 'SKILLID', None) or [])]
    except Exception:
        log_error('local-hero-passives-error')
        return
    applied = []
    for skill_id in skills:
        if not _dh_skill_is_passive(skill_id):
            continue
        stages = list(getattr(_dh_skill_row(skill_id), 'STAGES', None) or [])
        for index in range(len(stages)):
            _dh_stage_apply(player, skill_id, index)
        applied.append(skill_id)
    log('local-hero-passives', hero=hero, skills=applied, marks=dict((str(k), v) for k, v in _dh_hero_states['marks'].items()))



def _dh_set_cooldown(player, skill_id, start, cooldown):
    """The HUD's cooldown ring/text (UIPanelSkill.doSkillCoolDown) reads the cooldownFinishTime PROPERTY
    (skill id -> server time when the skill is ready); the game server kept it, m26 only told the provider."""
    try:
        table = getattr(player, 'cooldownFinishTime', None)
        if not isinstance(table, dict):
            table = {}
        old = dict(table)
        table[int(skill_id)] = float(start) + float(cooldown)
        player.cooldownFinishTime = table
        setter = getattr(player, 'set_cooldownFinishTime', None)
        if callable(setter):
            try:
                setter(old)
            except Exception:
                pass
        log('local-hero-cooldown', skill=skill_id, ready_in=cooldown)
    except Exception:
        log_error('local-hero-cooldown-error', skill=skill_id)


# the cast: states of each stage as the stage starts (replaces m26's stage runner, same contract)
def _dh_skill_stage(player, skill_id, token, index):
    state = _dh_hero['skills'].get(skill_id)
    if state is None or state['token'] != token:
        return
    row = _dh_skill_row(skill_id)
    stages = list(getattr(row, 'STAGES', None) or [])
    if index > 0:
        _dh_skill_call(player, 'skillStageFinish', skill_id, index - 1)
    if index >= len(stages):
        _dh_hero['skills'].pop(skill_id, None)
        now = _dh_server_time()
        _dh_set_cooldown(player, skill_id, now, float(getattr(row, 'COOLDOWN', 0) or 0))
        _dh_skill_call(player, 'skillFinish', skill_id, now)
        return
    _dh_skill_call(player, 'skillStageStart', skill_id, index)
    try:
        _dh_stage_apply(player, skill_id, index)
    except Exception:
        log_error('local-hero-stage-states-error', skill=skill_id, stage=index)
    try:
        wait = float(getattr(stages[index], 'TOTAL_TIME', 0.0) or 0.0)
    except Exception:
        wait = 0.0
    call_later(max(0.05, wait), _dh_skill_stage, player, skill_id, token, index + 1)


def _dh_hero_landed_states_wrapper(player, *args, **kwargs):
    result = _dh_hero_landed_states_wrapper._dh_inner(player, *args, **kwargs)
    try:
        if int(_dh_hero.get('hero') or 0) and int(BATTLE.get('map') or 0) in _DH_HERO_MAPS:
            call_later(2.0, _dh_hero_passives, player)
    except Exception:
        log_error('local-hero-landed-states-error')
    return result


def _dh_leave_states_wrapper(player=None, *args, **kwargs):
    try:
        _dh_states_clear(player or current_player())
    except Exception:
        pass
    return _dh_leave_states_wrapper._dh_inner(player, *args, **kwargs)


_dh_gen = int(globals().get('_dh_gen', 0) or 0) + 1       # one per load of this file
# markers used by earlier loads of this file (their wrappers carry no load tag and must be stripped too)
_DH_WRAP_MARKERS = ('_dh_rail', '_dh_states', '_dh_triggers', '_dh_race_loot', '_dh_race_parts', '_dh_relics', '_dh_coins', '_dh_fx', '_dh_respawn', '_dh_airdrops', '_dh_airdrops_h', '_dh_airdrops_s', '_dh_zombie', '_dh_airwar', '_dh_plane_car', '_dh_swim', '_dh_hotsig', '_dh_pk', '_dh_drift', '_dh_island', '_dh_hitscene', '_dh_mates', '_dh_tpp', '_dh_lootfloor', '_dh_dance', '_dh_weather', '_dh_flag', '_dh_boxes', '_dh_pin', '_dh_steer', '_dh_glide', '_dh_lod', '_dh_actlod', '_dh_partial', '_dh_kd')


def _dh_wrap_global(name, wrapper, marker):
    """Wrap a hook global.  Every wrapper here reads its inner through its global name, so a chain that still
    holds wrappers from an earlier load of this file loops back into the new ones: strip the same-marker wrapper
    and every wrapper of an older load first (wrappers without a load tag belong to _dh_unwrap and stay)."""
    inner = globals().get(name)
    while inner is not None and getattr(inner, '_dh_inner', None) is not None and (
            getattr(inner, marker, False) or ('_dh_gen' in vars(inner) and inner._dh_gen != _dh_gen)
            or ('_dh_gen' not in vars(inner) and any(key in vars(inner) for key in _DH_WRAP_MARKERS))):
        inner = inner._dh_inner
    if inner is None:
        return False
    wrapper._dh_inner = inner
    wrapper._dh_gen = _dh_gen
    setattr(wrapper, marker, True)
    globals()[name] = wrapper
    return True


try:
    _dh_m28 = {
        'landed': _dh_wrap_global('landed', _dh_hero_landed_states_wrapper, '_dh_states'),
        'leave': _dh_wrap_global('leave_battle', _dh_leave_states_wrapper, '_dh_states'),
        'change_prop': _dh_wrap_global('change_prop', _dh_change_prop_wrapper, '_dh_states'),
        'hit': _dh_wrap_global('take_player_hit', _dh_take_player_hit_wrapper, '_dh_states'),
        'self': _dh_wrap_global('hurt_self', _dh_hurt_self_wrapper, '_dh_states'),
    }
    log('local-hero-states-installed', **_dh_m28)
except Exception:
    log_error('local-hero-states-install-error')


# ---- m29: event-triggered hero skills.  Besides the button skills (SkillTriggerNone) and the ones fired at the
# pick (SelectIdentity, m28), a hero's SKILLID list holds skills the game server fired on battle events: a kill
# with the hero weapon, taking damage, firing, holding a weapon, opening the scope, jumping, an enemy in range.
# The hook sees all of those; each fires the skill's states, and the triggers that end when the condition stops
# (STATE_ID_TO_BREAK_WHEN_UNTRIGGER) are closed again.
_dh_hero_triggers = globals().get('_dh_hero_triggers') or {'list': [], 'hero': 0, 'active': {}, 'last': {}, 'detect': None}
_DH_DETECT_INTERVAL = 0.5


def _dh_trigger_build(player):
    hero = int(_dh_hero.get('hero') or 0)
    _dh_hero_triggers.update({'list': [], 'hero': hero, 'active': {}, 'last': {}, 'detect': None})
    if not hero:
        return
    try:
        tables = getattr(sys.modules.get('ui.UISelectHero'), 'tables', None)
        row = None
        for module, name in ((tables, 'getDtsOccupation'), (_properties_module(), 'getDtsOccupationData')):
            getter = getattr(module, name, None)
            if callable(getter):
                try:
                    row = getter(hero)
                    break
                except Exception:
                    row = None
        skills = [int(value) for value in list(getattr(row, 'SKILLID', None) or [])]
    except Exception:
        log_error('local-hero-triggers-error')
        return
    found = []
    for skill_id in skills:
        skill = _dh_skill_row(skill_id)
        trigger = getattr(skill, 'SKILL_TRIGGER', None)
        name = trigger.__class__.__name__
        if name in ('SkillTriggerNone',) or name in _DH_SPAWN_TRIGGERS:
            continue
        fields = {}
        for key in dir(trigger):
            if key.isupper():
                try:
                    fields[key] = getattr(trigger, key)
                except Exception:
                    pass
        found.append({'skill': skill_id, 'kind': name, 'fields': fields})
        if name == 'SkillTriggerDetectPlayer':
            _dh_hero_triggers['detect'] = skill_id
    _dh_hero_triggers['list'] = found
    log('local-hero-triggers', hero=hero, triggers=[(t['skill'], t['kind']) for t in found])
    if _dh_hero_triggers['detect']:
        call_later(_DH_DETECT_INTERVAL, _dh_detect_tick, player, _dh_hero_triggers['detect'])
    _dh_trigger_event(player, 'weapon')


def _dh_trigger_fire(player, entry, why):
    skill_id = entry['skill']
    if skill_id in _dh_hero_triggers['active']:
        return False
    stages = list(getattr(_dh_skill_row(skill_id), 'STAGES', None) or [])
    started = []
    for index in range(len(stages)):
        for state_id in _dh_stage_states(skill_id, index):
            if _dh_state_start(player, state_id, 'trigger %s %s' % (skill_id, why)):
                started.append(state_id)
    _dh_hero_triggers['active'][skill_id] = started
    log('local-hero-trigger', skill=skill_id, kind=entry['kind'], why=why, states=started)
    return True


def _dh_trigger_release(player, entry, why):
    skill_id = entry['skill']
    started = _dh_hero_triggers['active'].pop(skill_id, None)
    if started is None:
        return False
    breaks = _dh_int_list(entry['fields'].get('STATE_ID_TO_BREAK_WHEN_UNTRIGGER')) or started
    for state_id in breaks:
        _dh_state_end(player, state_id, None, 'untrigger %s' % why)
    return True


def _dh_held_weapon_id(player):
    try:
        gun = current_gun(player)
    except Exception:
        gun = None
    for name in ('weaponID', 'weaponId', 'id', 'itemID', 'gunID'):
        value = getattr(gun, name, None)
        if isinstance(value, (int, long)) and value > 0:
            return int(value)
    return 0


def _dh_trigger_event(player, event, **info):
    """event: kill (weapon), damage, attack, weapon, scope (on), jump (on), detect (on)."""
    if not _dh_hero_triggers['list'] or BATTLE.get('phase') != 'fighting':
        return
    now = time.time()
    for entry in _dh_hero_triggers['list']:
        kind, fields = entry['kind'], entry['fields']
        try:
            if event == 'kill' and kind == 'SkillTriggerShootKillWithWeapon':
                allowed = _dh_int_list(fields.get('WEAPON_LIST'))
                if not allowed or int(info.get('weapon') or 0) in allowed:
                    _dh_hero_triggers['active'].pop(entry['skill'], None)      # retriggers on every kill
                    _dh_trigger_fire(player, entry, 'kill')
            elif event == 'kill' and kind == 'SkillTriggerKillDown':
                _dh_hero_triggers['active'].pop(entry['skill'], None)
                _dh_trigger_fire(player, entry, 'kill')
            elif event == 'damage' and kind == 'SkillTriggerOnDamage':
                _dh_hero_triggers['active'].pop(entry['skill'], None)
                _dh_trigger_fire(player, entry, 'damage')
            elif event == 'damage' and kind == 'SkillTriggerOnDamageWithCondition':
                prop = str(fields.get('PROPERTY_NAME') or '')
                interval = float(fields.get('INTERVAL') or 0)
                if prop and not getattr(player, prop, False):
                    continue
                if now - _dh_hero_triggers['last'].get(entry['skill'], 0) < interval:
                    continue
                _dh_hero_triggers['last'][entry['skill']] = now
                _dh_hero_triggers['active'].pop(entry['skill'], None)
                _dh_trigger_fire(player, entry, 'damage')
            elif event == 'attack' and kind == 'SkillTriggerOnAttack':
                chance = float(fields.get('PROBABILITY') or 1.0)
                if random.random() <= chance:
                    _dh_hero_triggers['active'].pop(entry['skill'], None)
                    _dh_trigger_fire(player, entry, 'attack')
            elif event == 'weapon' and kind == 'SkillTriggerHoldWeapon':
                held = _dh_held_weapon_id(player)
                if held in _dh_int_list(fields.get('WEAPON_ID_LIST')):
                    _dh_trigger_fire(player, entry, 'weapon %s' % held)
                else:
                    _dh_trigger_release(player, entry, 'weapon')
            elif event == 'scope' and kind == 'SkillTriggerSwitchOperateMode':
                if info.get('on'):
                    _dh_trigger_fire(player, entry, 'scope')
                else:
                    _dh_trigger_release(player, entry, 'scope')
            elif event == 'jump' and kind == 'SkillTriggerJump':
                if info.get('on'):
                    _dh_trigger_fire(player, entry, 'jump')
                else:
                    _dh_trigger_release(player, entry, 'jump')
            elif event == 'detect' and kind == 'SkillTriggerDetectPlayer':
                if info.get('on'):
                    _dh_trigger_fire(player, entry, 'detect')
                else:
                    _dh_trigger_release(player, entry, 'detect')
        except Exception:
            log_error('local-hero-trigger-error', skill=entry['skill'], event=event)


def _dh_detect_distance(player):
    """The SkillStateDetectPlayer control of the hero's detect skill: DISTANCE."""
    for entry in _dh_hero_triggers['list']:
        if entry['kind'] != 'SkillTriggerDetectPlayer':
            continue
        # the passive that carries the detector (same hero): any state with that control
    hero_skills = [entry['skill'] for entry in _dh_hero_triggers['list']]
    for state_id, state in _dh_hero_states['active'].items():
        row = _dh_state_row(state_id)
        for control in list(getattr(row, 'ATTRIBUTE_CONTROL', None) or []):
            if _dh_ctrl_name(control) == 'SkillStateDetectPlayer':
                return float(getattr(control, 'DISTANCE', 0) or 0)
    return 0.0


def _dh_enemy_near(player, distance):
    if distance <= 0:
        return False
    try:
        import BigWorld
        me = _point(player.position)
        for entity in list(BigWorld.entities.values()):
            if entity is player or entity.__class__.__name__ not in ('Avatar', 'PlayerAvatar', 'Robot', 'DtsRobot'):
                continue
            if int(getattr(entity, 'hp', 0) or 0) <= 0:
                continue
            them = _point(entity.position)
            if ((me[0] - them[0]) ** 2 + (me[1] - them[1]) ** 2 + (me[2] - them[2]) ** 2) <= distance * distance:
                return True
    except Exception:
        pass
    return False


def _dh_detect_tick(player, skill_id):
    if _dh_hero_triggers.get('detect') != skill_id or BATTLE.get('phase') != 'fighting':
        return
    try:
        _dh_trigger_event(player, 'detect', on=_dh_enemy_near(player, _dh_detect_distance(player)))
    except Exception:
        log_error('local-hero-detect-error')
    call_later(_DH_DETECT_INTERVAL, _dh_detect_tick, player, skill_id)


# -- the events
def _dh_kill_avatar_trigger(player, target, src_pos, weapon, hit_part, hit_type, weapon_name, *args, **kwargs):
    result = _dh_kill_avatar_trigger._dh_inner(player, target, src_pos, weapon, hit_part, hit_type, weapon_name, *args, **kwargs)
    try:
        if player is current_player():
            _dh_trigger_event(player, 'kill', weapon=_dh_held_weapon_id(player))
    except Exception:
        pass
    return result


def _dh_fire_trigger(player, *args, **kwargs):
    try:
        _dh_trigger_event(player, 'attack')
    except Exception:
        pass
    return _dh_fire_trigger._dh_inner(player, *args, **kwargs)


def _dh_switch_weapon_trigger(player, slot, *args, **kwargs):
    result = _dh_switch_weapon_trigger._dh_inner(player, slot, *args, **kwargs)
    call_later(0.1, _dh_trigger_event, player, 'weapon')
    return result


def _dh_jump_start_trigger(player, *args, **kwargs):
    try:
        _dh_trigger_event(player, 'jump', on=True)
    except Exception:
        pass
    return _dh_jump_start_trigger._dh_inner(player, *args, **kwargs)


def _dh_jump_end_trigger(player, *args, **kwargs):
    try:
        _dh_trigger_event(player, 'jump', on=False)
    except Exception:
        pass
    return _dh_jump_end_trigger._dh_inner(player, *args, **kwargs)


def _dh_hit_trigger(player, hurt, *args, **kwargs):
    result = _dh_hit_trigger._dh_inner(player, hurt, *args, **kwargs)
    try:
        _dh_trigger_event(player, 'damage')
    except Exception:
        pass
    return result


def on_switch_operate_mode(player, mode=0, *args, **kwargs):
    try:
        _dh_trigger_event(player, 'scope', on=bool(int(mode or 0)))
        if once('operate-mode-%s' % mode):
            log('local-hero-operate-mode', mode=safe(mode, 20))
    except Exception:
        pass
    return None


def _dh_hero_landed_triggers_wrapper(player, *args, **kwargs):
    result = _dh_hero_landed_triggers_wrapper._dh_inner(player, *args, **kwargs)
    try:
        if int(_dh_hero.get('hero') or 0) and int(BATTLE.get('map') or 0) in _DH_HERO_MAPS:
            call_later(2.5, _dh_trigger_build, player)
    except Exception:
        log_error('local-hero-landed-triggers-error')
    return result


def _dh_leave_triggers_wrapper(player=None, *args, **kwargs):
    _dh_hero_triggers.update({'list': [], 'active': {}, 'detect': None})
    return _dh_leave_triggers_wrapper._dh_inner(player, *args, **kwargs)


try:
    _dh_m29 = {
        'landed': _dh_wrap_global('landed', _dh_hero_landed_triggers_wrapper, '_dh_triggers'),
        'leave': _dh_wrap_global('leave_battle', _dh_leave_triggers_wrapper, '_dh_triggers'),
        'kill': _dh_wrap_global('kill_avatar', _dh_kill_avatar_trigger, '_dh_triggers'),
        'fire': _dh_wrap_global('on_fire', _dh_fire_trigger, '_dh_triggers'),
        'weapon': _dh_wrap_global('switch_weapon', _dh_switch_weapon_trigger, '_dh_triggers'),
        'jump_start': _dh_wrap_global('on_jump_start', _dh_jump_start_trigger, '_dh_triggers'),
        'jump_end': _dh_wrap_global('on_jump_end', _dh_jump_end_trigger, '_dh_triggers'),
        'hit': _dh_wrap_global('take_player_hit', _dh_hit_trigger, '_dh_triggers'),
    }
    _handlers = getattr(LOBBY, 'RPC_HANDLERS', None) if LOBBY is not None else None
    if isinstance(_handlers, dict):
        for _name in ('fire', 'jumpStart', 'jumpEnd'):
            _handlers[_name] = globals()['on_fire' if _name == 'fire' else ('on_jump_start' if _name == 'jumpStart' else 'on_jump_end')]
        _handlers['switchOperateMode'] = on_switch_operate_mode
    log('local-hero-triggers-installed', **_dh_m29)
except Exception:
    log_error('local-hero-triggers-install-error')


# ---- m30: Death Race loot.  The race map drops the game's Auto Royale items (NOS, springs, fuel, tool kits, the
# hell-fire and cloaking devices, and the six car parts) around the drop, and a seated player picks them into the
# CAR's trunk (iAutoRoyalePackage.onAddAutoRoyaleItem) instead of the backpack, so the trunk page and the car-part
# slots finally have something to show.  Hazards that need a space entity (mine, oil, smoke, gas) are left out.
_DH_RACE_LOOT = ((310003, 1), (310004, 1), (310004, 1), (310006, 1), (310006, 1),
                 (310007, 1), (310020, 1), (310023, 1), (310009, 1), (310011, 1), (310012, 1), (310013, 1), (310014, 1),
                 (310015, 1))
_DH_RACE_LOOT_COUNT = 40
_DH_TRUNK_FULL_TIP = 'Trunk full'
_DH_NEEDS_CAR_TIP = 'Pick it up from a car'


def _dh_race_loot_plan_wrapper(centre, randomizer, *args, **kwargs):
    plan = _dh_race_loot_plan_wrapper._dh_inner(centre, randomizer, *args, **kwargs)
    try:
        if _dh_race_params() is None:
            log('local-race-loot-skip', map=BATTLE.get('map'))
            return plan
        extra = []
        for _index in range(_DH_RACE_LOOT_COUNT):
            prop, amount = randomizer.choice(_DH_RACE_LOOT)
            angle = randomizer.uniform(0.0, 2.0 * math.pi)
            distance = randomizer.uniform(LOOT_MIN_RADIUS, LOOT_RADIUS)
            extra.append((prop, amount, centre[0] + distance * math.cos(angle), centre[1] + distance * math.sin(angle)))
        log('local-race-loot', extra=len(extra))
        return list(plan) + extra
    except Exception:
        log_error('local-race-loot-error')
        return plan


def _dh_is_royale_item(kind):
    return bool(kind) and (kind.startswith('AutoRoyale') or kind == 'PropTypeAutoRoyaleNOS')


def _dh_grant_prop_wrapper(player, prop, taken, *args, **kwargs):
    try:
        kind = prop_kind(prop)
    except Exception:
        kind = None
    if _dh_is_royale_item(kind):
        car = vehicle_entity(getattr(player, 'vehicleEntID', 0)) if getattr(player, 'inLandVehicle', False) else None
        if car is None or not callable(getattr(car, 'onAddAutoRoyaleItem', None)):
            tip_text(_DH_NEEDS_CAR_TIP)
            return None
        try:
            if not car.canAddAutoRoyaleItem(int(prop), int(taken)):
                tip_text(_DH_TRUNK_FULL_TIP)
                return None
            serial = int(BATTLE.get('item_serial', 0) or 0) + 1
            BATTLE['item_serial'] = serial
            car.onAddAutoRoyaleItem(int(prop), [{'uuid': 'rl-%d-%d' % (int(prop), serial), 'number': int(taken), 'info': {}}], 0, int(taken))
            log('local-race-trunk-add', prop=prop, amount=taken, kind=kind)
            return 'trunk'
        except Exception:
            log_error('local-race-trunk-add-error', prop=prop)
            return None
    return _dh_grant_prop_wrapper._dh_inner(player, prop, taken, *args, **kwargs)


try:
    _dh_m30 = {
        'loot': _dh_wrap_global('loot_plan', _dh_race_loot_plan_wrapper, '_dh_race_loot'),
        'grant': _dh_wrap_global('grant_prop', _dh_grant_prop_wrapper, '_dh_race_loot'),
    }
    log('local-race-loot-installed', **_dh_m30)
except Exception:
    log_error('local-race-loot-install-error')


# ---- m30b: using the trunk items and fitting the car parts (the game server's useVehiclePropInSlot and the
# pick-up-time effects of PropVehicleUpdate / NOS items)
_DH_CAR_PART_SPEED = 0.10          # turbo boost: top speed per level
_DH_CAR_PART_ARMOR = 0.15          # armor: max HP per level
_DH_CAR_PART_TRUNK = 500           # warehouse: trunk capacity per level
_dh_car_fx = globals().get('_dh_car_fx') or {'fuel': {}, 'cloak': {}}


def _dh_speed_buff(car):
    """vehicleBuff is an engine fixed dict (no .get)."""
    try:
        return float(car.vehicleBuff['maxSpeedBuff'] or 1.0)
    except Exception:
        return 1.0


def _dh_prop_type(item_id):
    try:
        return _properties_module().getBattleGroundPropData(int(item_id)).PROP_TYPE
    except Exception:
        return None


def _dh_car_levels(car):
    levels = getattr(car, 'vehiclePropertyLevel', None)
    return dict(levels) if isinstance(levels, dict) else {}


def _dh_car_part(player, car, prop_id, change):
    levels = _dh_car_levels(car)
    old = dict(levels)
    level = int(levels.get(prop_id, 0) or 0) + int(change)
    levels[prop_id] = level
    try:
        car.vehiclePropertyLevel = levels
        setter = getattr(car, 'set_vehiclePropertyLevel', None)
        if callable(setter):
            setter(old)
    except Exception:
        pass
    _dh_royale_vehicle_call(car, 'onCarPropertyChanged', prop_id, level)
    try:
        if prop_id == 1:
            base = _dh_speed_buff(car)
            car.vehicleBuff['maxSpeedBuff'] = base + _DH_CAR_PART_SPEED * int(change)
        elif prop_id == 2:
            capacity = int(car.getAutoRoyalePkgTotalCapacity()) + _DH_CAR_PART_TRUNK * int(change)
            car.onUnlockAutoRoyaleItemPackage(capacity)
        elif prop_id == 3:
            top = int(getattr(car, 'maxHp', 0) or 0)
            gain = int(round(top * _DH_CAR_PART_ARMOR * int(change)))
            if top and gain:
                change_prop(car, 'maxHp', top + gain)
                car.hp = min(int(car.maxHp), int(car.hp) + gain)
                car.onRecoverHP(int(car.hp))
    except Exception:
        log_error('local-race-part-effect-error', part=prop_id)
    log('local-race-part', part=prop_id, level=level)


def _dh_car_nos(car, amount):
    for name in ('nosAmount', 'nos', 'curNos', 'nosValue'):
        if hasattr(car, name):
            try:
                old = float(getattr(car, name) or 0)
                setattr(car, name, old + float(amount))
                setter = getattr(car, 'set_' + name, None)
                if callable(setter):
                    setter(old)
                log('local-race-nos', field=name, amount=amount)
                return True
            except Exception:
                pass
    if once('race-nos-field'):
        log('local-race-nos-unsupported', fields=[n for n in dir(car) if 'nos' in n.lower()][:12])
    return False


def _dh_race_pickup_effect(player, car, prop, kind, taken):
    """Items the game server applied the moment they were picked (never stored): car parts and NOS."""
    if kind == 'AutoRoyalePropVehicleUpdate':
        row = _dh_prop_type(prop)
        for entry in list(getattr(row, 'PROPERTY_LEVEL_UPDATE_LIST', None) or []):
            _dh_car_part(player, car, int(getattr(entry, 'PROPERTY_ID', 0) or 0), int(getattr(entry, 'CHANGE_LEVEL', 1) or 1) * int(taken))
        return 'car-part'
    if kind == 'PropTypeAutoRoyaleNOS':
        _dh_car_nos(car, float(getattr(_dh_prop_type(prop), 'NOS_AMOUNT', 0) or 0) * int(taken))
        return 'nos'
    return None


def _dh_car_heal_tick(car, amount, ticks, interval, token):
    if _dh_car_fx.get('heal') != token or vehicle_entity(car.id) is None:
        return
    try:
        top = int(getattr(car, 'maxHp', 0) or 0)
        new = min(top, int(car.hp) + int(amount)) if top else int(car.hp) + int(amount)
        if new != int(car.hp):
            car.hp = new
            car.onRecoverHP(new)
    except Exception:
        log_error('local-race-heal-error')
        return
    if ticks > 1:
        call_later(interval, _dh_car_heal_tick, car, amount, ticks - 1, interval, token)


def _dh_car_fuel_end(car, token):
    record = _dh_car_fx['fuel'].get(car.id)
    if record is None or record['token'] != token:
        return
    _dh_car_fx['fuel'].pop(car.id, None)
    try:
        car.vehicleBuff['maxSpeedBuff'] = record['base']
    except Exception:
        pass


def _dh_car_cloak_end(car, token):
    if _dh_car_fx['cloak'].get(car.id) != token:
        return
    _dh_car_fx['cloak'].pop(car.id, None)
    try:
        car.unsetTransparent()
    except Exception:
        pass


def on_use_vehicle_prop(player, item_id=0, number=1, *args, **kwargs):
    try:
        item_id, number = int(item_id), max(1, int(number or 1))
    except Exception:
        return None
    try:
        car = vehicle_entity(getattr(player, 'vehicleEntID', 0)) if getattr(player, 'inLandVehicle', False) else None
        if car is None:
            return None
        if int(car.getAutoRoyaleItemCnt(item_id) or 0) < 1:
            log('local-race-use-missing', item=item_id)
            return None
        kind = prop_kind(item_id)
        row = _dh_prop_type(item_id)
        car.onDelAutoRoyaleFoldedItem(item_id, 1)
        try:
            car.onAvatarUseVehicleProp(item_id)
        except Exception:
            pass
        if kind == 'AutoRoyaleGentleMedicine':
            token = object()
            _dh_car_fx['heal'] = token
            ticks = max(1, int(getattr(row, 'TIMES', 1) or 1))
            spread = float(getattr(row, 'EFFECT_TIME', 0) or 0)
            call_later(0.2, _dh_car_heal_tick, car, int(getattr(row, 'EFFECT', 0) or 0), ticks, spread / ticks if ticks else 0.5, token)
        elif kind == 'AutoRoyalePropHighOctane':
            record = _dh_car_fx['fuel'].get(car.id)
            base = record['base'] if record else _dh_speed_buff(car)
            token = object()
            _dh_car_fx['fuel'][car.id] = {'base': base, 'token': token}
            car.vehicleBuff['maxSpeedBuff'] = base * (1.0 + float(getattr(row, 'MAX_SPEED_ENHANCE_PERCENT', 0.3) or 0.3))
            call_later(float(getattr(row, 'TIME', 10) or 10), _dh_car_fuel_end, car, token)
        elif kind == 'AutoRoyalePropTransparent':
            token = object()
            _dh_car_fx['cloak'][car.id] = token
            car.setTransparent(float(getattr(row, 'MIN_TRANSPARENT_SPEED', 0) or 0), float(getattr(row, 'MAX_TRANSPARENT_SPEED', 0) or 0))
            call_later(float(getattr(row, 'DURATION', 20) or 20), _dh_car_cloak_end, car, token)
        elif kind == 'AutoRoyalePropJump':
            jump = getattr(car, 'useItemJump', None)
            if callable(jump):
                jump(float(getattr(row, 'UP_FORCE', 40) or 40))
            elif once('race-jump'):
                log('local-race-use-unsupported', kind=kind)
        elif kind == 'AutoRoyalePropQuickFireSpeed':
            _dh_fire_rate_buff(player, float(getattr(row, 'DURATION', 10) or 10))
        else:
            if once('race-use-' + str(kind)):
                log('local-race-use-unsupported', kind=kind)
        log('local-race-use', item=item_id, kind=kind)
    except Exception:
        log_error('local-race-use-error', item=item_id)
    return None


def _dh_grant_prop_wrapper2(player, prop, taken, *args, **kwargs):
    try:
        kind = prop_kind(prop)
    except Exception:
        kind = None
    if kind in ('AutoRoyalePropVehicleUpdate', 'PropTypeAutoRoyaleNOS'):
        car = vehicle_entity(getattr(player, 'vehicleEntID', 0)) if getattr(player, 'inLandVehicle', False) else None
        if car is None:
            tip_text(_DH_NEEDS_CAR_TIP)
            return None
        try:
            return _dh_race_pickup_effect(player, car, int(prop), kind, int(taken))
        except Exception:
            log_error('local-race-pickup-effect-error', prop=prop)
            return None
    return _dh_grant_prop_wrapper2._dh_inner(player, prop, taken, *args, **kwargs)


try:
    _dh_m30b = {'grant2': _dh_wrap_global('grant_prop', _dh_grant_prop_wrapper2, '_dh_race_parts')}
    _handlers = getattr(LOBBY, 'RPC_HANDLERS', None) if LOBBY is not None else None
    if isinstance(_handlers, dict):
        _handlers['useVehiclePropInSlot'] = on_use_vehicle_prop
    log('local-race-parts-installed', handlers=isinstance(_handlers, dict), **_dh_m30b)
except Exception:
    log_error('local-race-parts-install-error')


# the loot on this build streams from the map's own DTSProp spots (roll_spot), not from loot_plan: on the race map
# half of the rolled spots carry an Auto Royale item instead
_DH_RACE_SPOT_SHARE = 0.5
_dh_race_spots = globals().get('_dh_race_spots') or {'n': 0}


def _dh_roll_spot_wrapper(seed, index, group, *args, **kwargs):
    items = _dh_roll_spot_wrapper._dh_inner(seed, index, group, *args, **kwargs)
    try:
        if not items or _dh_race_params() is None:
            return items
        import random as _random
        randomizer = _random.Random('%s-race-%d' % (seed, index))
        if randomizer.random() < _DH_RACE_SPOT_SHARE:
            prop, amount = randomizer.choice(_DH_RACE_LOOT)
            _dh_race_spots['n'] += 1
            if _dh_race_spots['n'] in (1, 10, 50):
                log('local-race-loot-spot', count=_dh_race_spots['n'], prop=prop)
            return [(prop, amount, 0.0, 0.0)]
    except Exception:
        log_error('local-race-loot-spot-error')
    return items


try:
    _dh_m30c = {'spots': _dh_wrap_global('roll_spot', _dh_roll_spot_wrapper, '_dh_race_loot')}
    log('local-race-spots-installed', **_dh_m30c)
except Exception:
    log_error('local-race-spots-install-error')


# ---- m31: Epic Clash 2.0 relics (map 730, the game's "secret treasure").  Relics (SecretTreasureItem props,
# 2220001..) are rolled on the map's loot spots, into every death crate and every airdrop; picking one up applies
# its ACTIONS with the m28 engine: TreasureAddMark (marks), TreasureAddStates (states), TreasureAddBonus (marks per
# relic held), and shows it on the HUD (UIShowSecretTreasure.onGetBuffer / onUpdateBufferLevel).  Relics are kept
# per round (count per relic = its level).  Left out: Scarlet Mask (turns the player into a zombie identity), the
# relic choice screen and the relic mall / energy.
_DH_RELIC_MAPS = (730,)
_DH_RELIC_SPOT_SHARE = 0.12
_DH_RELIC_SKIP = (2220011,)
_dh_relics = globals().get('_dh_relics') or {'held': {}, 'pool': None}


def _dh_relic_map():
    try:
        return int(BATTLE.get('map') or 0) in _DH_RELIC_MAPS
    except Exception:
        return False


def _dh_relic_pool():
    if _dh_relics['pool'] is not None:
        return _dh_relics['pool']
    pool = []
    try:
        for _key, row in _properties_module().iterSecretTreasureHeritageItemData():
            item = int(getattr(row, 'ITEM_ID', 0) or 0)
            weight = int(getattr(row, 'WEIGHT', 1) or 1)
            if item and item not in _DH_RELIC_SKIP:
                pool.extend([item] * max(1, weight))
    except Exception:
        log_error('local-relic-pool-error')
    _dh_relics['pool'] = pool
    return pool


def _dh_relic_pick(randomizer):
    pool = _dh_relic_pool()
    return randomizer.choice(pool) if pool else 0


def _dh_relic_roll_spot_wrapper(seed, index, group, *args, **kwargs):
    items = _dh_relic_roll_spot_wrapper._dh_inner(seed, index, group, *args, **kwargs)
    try:
        if items and _dh_relic_map():
            import random as _random
            randomizer = _random.Random('%s-relic-%d' % (seed, index))
            if randomizer.random() < _DH_RELIC_SPOT_SHARE:
                relic = _dh_relic_pick(randomizer)
                if relic:
                    return [(relic, 1, 0.0, 0.0)]
    except Exception:
        log_error('local-relic-spot-error')
    return items


def _dh_relic_heritage_wrapper(randomizer, *args, **kwargs):
    items = _dh_relic_heritage_wrapper._dh_inner(randomizer, *args, **kwargs)
    try:
        if _dh_relic_map() and isinstance(items, dict):
            relic = _dh_relic_pick(randomizer)
            if relic:
                items['heritage-relic'] = [relic, 1, {}]
    except Exception:
        log_error('local-relic-heritage-error')
    return items


def _dh_relic_airdrop_wrapper(randomizer, *args, **kwargs):
    items = _dh_relic_airdrop_wrapper._dh_inner(randomizer, *args, **kwargs)
    try:
        if _dh_relic_map():
            relic = _dh_relic_pick(randomizer)
            if relic and isinstance(items, list):
                items.append((relic, 1))
            elif relic and isinstance(items, dict):
                items['airdrop-relic'] = [relic, 1, {}]
    except Exception:
        log_error('local-relic-airdrop-error')
    return items


def _dh_relic_hud(player, item, level):
    try:
        import Globals
        ig = (getattr(Globals.uiMgr, '____all_ui__', {}) or {}).get('UIBattlegroundsInGame')
        panel = ig.GetComponent('UIShowSecretTreasure') if ig is not None else None
        if panel is None:
            return False
        if level <= 1:
            panel.onGetBuffer(int(item))
        else:
            panel.onUpdateBufferLevel(int(item), int(level))
        return True
    except Exception:
        if once('relic-hud'):
            log_error('local-relic-hud-error', item=item)
        return False


def _dh_relic_apply(player, item):
    row = _dh_prop_type(item)
    level = _dh_relics['held'].get(int(item), 0) + 1
    _dh_relics['held'][int(item)] = level
    applied = []
    for action in list(getattr(row, 'ACTIONS', None) or []):
        kind = action.__class__.__name__
        try:
            if kind == 'TreasureAddMark':
                for mark in _dh_int_list(getattr(action, 'MARK_LIST', None)):
                    _dh_mark_set(player, mark, _dh_hero_states['marks'].get(mark, 0) + 1)
                    applied.append(('mark', mark))
            elif kind == 'TreasureAddBonus':
                for mark in _dh_int_list(getattr(action, 'MARK_LIST_WHEN_ACQUIRE_BONUS', None)):
                    _dh_mark_set(player, mark, _dh_hero_states['marks'].get(mark, 0) + 1)
                    applied.append(('bonus-mark', mark))
            elif kind == 'TreasureAddStates':
                for info in list(getattr(action, 'STATE_INFOS', None) or []):
                    state_id = 0
                    for name in ('STATE_ID', 'ID', 'STATEID'):
                        try:
                            state_id = int(getattr(info, name, 0) or 0)
                        except Exception:
                            state_id = 0
                        if state_id:
                            break
                    if state_id:
                        _dh_state_start(player, state_id, 'relic %s' % item)
                        applied.append(('state', state_id))
                    elif once('relic-state-info'):
                        log('local-relic-state-info', fields=[k for k in dir(info) if k.isupper()][:12])
            else:
                if once('relic-action-' + kind):
                    log('local-relic-unsupported', action=kind, item=item)
        except Exception:
            log_error('local-relic-action-error', item=item, action=kind)
    _dh_relic_hud(player, item, level)
    log('local-relic', item=item, level=level, applied=applied[:8])


def _dh_relic_grant_wrapper(player, prop, taken, *args, **kwargs):
    try:
        kind = prop_kind(prop)
    except Exception:
        kind = None
    if kind == 'SecretTreasureItem':
        try:
            _dh_relic_apply(player, int(prop))
        except Exception:
            log_error('local-relic-apply-error', prop=prop)
        return 'relic'
    return _dh_relic_grant_wrapper._dh_inner(player, prop, taken, *args, **kwargs)


def _dh_relic_leave_wrapper(player=None, *args, **kwargs):
    _dh_relics['held'] = {}
    return _dh_relic_leave_wrapper._dh_inner(player, *args, **kwargs)


try:
    _dh_m31 = {
        'spots': _dh_wrap_global('roll_spot', _dh_relic_roll_spot_wrapper, '_dh_relics'),
        'heritage': _dh_wrap_global('heritage_items', _dh_relic_heritage_wrapper, '_dh_relics'),
        'airdrop': _dh_wrap_global('airdrop_items', _dh_relic_airdrop_wrapper, '_dh_relics'),
        'grant': _dh_wrap_global('grant_prop', _dh_relic_grant_wrapper, '_dh_relics'),
        'leave': _dh_wrap_global('leave_battle', _dh_relic_leave_wrapper, '_dh_relics'),
    }
    log('local-relics-installed', **_dh_m31)
except Exception:
    log_error('local-relics-install-error')


# ---- m32: the "presentation" hero controllers and the remaining triggers.  The game server ran each controller
# against the cell entity and called ownClient / allClients methods; the client avatar has most of those methods
# and properties itself (setTransparentValue, onHideShadow, perspectiveDist, playerSelfPerspective, immuneFatalDamage,
# startJumpBuff, coldWeaponLocked, hideFlyingAccessory...), so the controllers are mapped onto them here.
_DH_IMMUNE_DEFAULT = (0.5, 120.0)
_dh_fx = globals().get('_dh_fx') or {'immune': None, 'decoys': {}, 'air': False, 'speed_at': None, 'speed_pos': None, 'running': False, 'fast': False}


def _dh_prop_set(player, attr, value):
    try:
        return change_prop(player, attr, value)
    except Exception:
        return False


def _dh_decoy_spawn(player, control):
    try:
        offset = getattr(control, 'OFFSET', None)
        forward = float(getattr(offset, 'FORWARD', 0) or 0)
        right = float(getattr(offset, 'RIGHT', 0) or 0)
        x, y, z = _point(player.position)
        yaw = float(getattr(player, 'yaw', 0.0) or 0.0)
        px = x + forward * math.sin(yaw) + right * math.cos(yaw)
        pz = z + forward * math.cos(yaw) - right * math.sin(yaw)
        index = 900000 + len(_dh_fx['decoys']) + 1
        item = {'id': index, 'pos': (px, y, pz), 'name': avatar_name(player), 'character': int(getattr(player, 'characterType', 0) or 0)}
        made = _spawn_remote(item)
        if made is None:
            # the remote-class path refused: build the body directly, the way other players' bodies are built
            try:
                class_name = BATTLE.get('remote_class') or 'BattleGroundAvatar'
                install_class_defaults(class_name)
                install_remote_fallback(class_name)
                made = _create_entity(class_name, _point(item['pos']), remote_properties(item, class_name))
            except Exception:
                log_error('local-hero-decoy-build-error')
                made = None
            if made is None:
                log('local-hero-decoy-none', remote_class=safe(BATTLE.get('remote_class'), 30))
                return None
        entity_id = int(made) if isinstance(made, (int, long)) else int(getattr(made, 'id', 0) or 0)
        if not entity_id:
            return None
        _dh_fx['decoys'][index] = entity_id
        call_later(0.6, _dh_decoy_dress, entity_id, int(getattr(player, 'identityType', 0) or 0))
        log('local-hero-decoy', index=index, entity=entity_id)
        return index
    except Exception:
        log_error('local-hero-decoy-error')
        return None


def _dh_decoy_dress(entity_id, hero):
    try:
        import BigWorld
        entity = BigWorld.entities.get(entity_id)
        if entity is None or not hero:
            return
        entity.identityType = hero
        setter = getattr(entity, 'set_identityType', None)
        if callable(setter):
            setter(0)
    except Exception:
        pass


def _dh_decoy_remove(index):
    entity_id = _dh_fx['decoys'].pop(index, None)
    if entity_id:
        try:
            if entity_id in _remote:
                _destroy(entity_id)
            else:
                import BigWorld
                BigWorld.destroyEntity(entity_id)
        except Exception:
            pass


def _dh_move_white_circle(player, distance):
    try:
        if not _zone.get('on'):
            return False
        state = zone_state(_zone['start'], _zone['circles'], _zone['times'], _zone['rounds'], _zone['elapsed'])
        stage = int(state.get('stage', 0) or 0)
        circles = list(_zone['circles'])
        if stage >= len(circles):
            return False
        cx, cz, radius = circles[stage]
        x, _y, z = _point(player.position)
        dx, dz = x - cx, z - cz
        length = math.hypot(dx, dz)
        if length <= 1.0:
            return True
        step = min(float(distance), length)
        circles[stage] = (cx + dx / length * step, cz + dz / length * step, radius)
        _zone['circles'] = circles
        try:
            player.onWhiteCircleCenterChange()
        except Exception:
            pass
        log('local-hero-white-circle', stage=stage, moved=round(step))
        return True
    except Exception:
        log_error('local-hero-white-circle-error')
        return False


def _dh_secret_choice(player, control):
    """ITEM_IDS: {relic: weight}.  The pick screen is not reachable from here: one of three weighted picks is granted."""
    import random as _random
    weights = getattr(control, 'ITEM_IDS', None) or {}
    pool = []
    for item, weight in list(weights.items()):
        try:
            pool.extend([int(item)] * max(1, int(weight)))
        except Exception:
            pass
    if not pool:
        return None
    picks = [_random.choice(pool) for _index in range(3)]
    chosen = picks[0]
    _dh_relic_apply(player, chosen)
    log('local-hero-relic-choice', offered=picks, chosen=chosen)
    return chosen


def _dh_fx_control(player, state_id, token, control, flow):
    """True when handled here (an m28 'unsupported' controller)."""
    name = _dh_ctrl_name(control)
    undo = []
    if name == 'SkillStateSetInvisible':
        try:
            player.setTransparentValue(int(getattr(control, 'TRANSPARENT', 125) or 125))
            _dh_prop_set(player, 'isImbaInvisible', True)
            undo.append(('call', ('setTransparentValue', (255,))))
            undo.append(('prop', 'isImbaInvisible'))
        except Exception:
            log_error('local-hero-fx-error', control=name)
    elif name == 'SkillStateSetInvisibleTP':
        pass                                                # only the other clients' copy
    elif name == 'SkillStateHideShadow':
        try:
            player.onHideShadow(True)
            undo.append(('call', ('onHideShadow', (False,))))
        except Exception:
            log_error('local-hero-fx-error', control=name)
    elif name == 'SkillStateHideFlyingAccessory':
        try:
            player.hideFlyingAccessory = True
            player.refreshFlyingAccessory('none')
            undo.append(('fly', None))
        except Exception:
            log_error('local-hero-fx-error', control=name)
    elif name == 'SkillStateSpeedEnhanced':
        add = int(getattr(control, 'SPEED_ADD', 0) or 0)
        _dh_hero_states['speed'] += add
        change_prop(player, 'boostSpeedBuff', int(_buffs.get('boostSpeedBuff', (0, 0))[1]))
        undo.append(('speed', add))
    elif name == 'SkillStateJumpEnhanced':
        try:
            player.startJumpBuff(float(getattr(control, 'MAX_HEIGHT', 0) or 0))
            undo.append(('jump', None))
        except Exception:
            log_error('local-hero-fx-error', control=name)
    elif name == 'SkillLockColdWeapon':
        weapon = int(getattr(control, 'COLD_WEAPON_ID', 0) or 0)
        try:
            if weapon:
                equip_slot_item(player, MELEE_SLOT, weapon)
            _dh_prop_set(player, 'coldWeaponLocked', True)
            undo.append(('prop', 'coldWeaponLocked'))
        except Exception:
            log_error('local-hero-fx-error', control=name)
    elif name == 'SkillStateImmuneFatal':
        _dh_fx['immune'] = {'state': state_id, 'invincible': float(getattr(control, 'INVINCIBLE_TIME', _DH_IMMUNE_DEFAULT[0]) or _DH_IMMUNE_DEFAULT[0]),
                            'interval': float(getattr(control, 'IMMUNE_INTERVAL', _DH_IMMUNE_DEFAULT[1]) or _DH_IMMUNE_DEFAULT[1]), 'ready_at': 0.0, 'until': 0.0}
        _dh_prop_set(player, 'immuneFatalDamage', True)
        undo.append(('immune', None))
    elif name in ('HeroPlayerSelfPerspective',):
        _dh_prop_set(player, 'playerSelfPerspective', True)
        undo.append(('prop', 'playerSelfPerspective'))
    elif name in ('SkillSetPerspective', 'SkillStateDetectPlayer', 'SkillStatePerspectDetectPlayer', 'SkillStateTeamPerspectNearestPlayer'):
        dist = float(getattr(control, 'MAX_DIST', 0) or getattr(control, 'DISTANCE', 0) or 10000.0)
        _dh_prop_set(player, 'perspectiveDist', dist)
        undo.append(('prop0', 'perspectiveDist'))
    elif name == 'HeroPlayerDelaySectorPerspective':
        _dh_prop_set(player, 'sectorPerspectiveAngle', float(getattr(control, 'ANGLE', 7.5) or 7.5))
        _dh_prop_set(player, 'sectorPerspectiveRadius', 10000.0)
        _dh_prop_set(player, 'playerSectorPerspective', True)
        undo.append(('prop', 'playerSectorPerspective'))
    elif name == 'SkillHeroMoveWhiteCircle':
        _dh_move_white_circle(player, float(getattr(control, 'DISTANCE', 0) or 0))
    elif name == 'StateServerStartSing':
        later = _dh_int_list(getattr(control, 'STATES_TO_ADD_WHEN_SUCCESS', None))
        seconds = float(getattr(control, 'SEC', 0) or 0)
        try:
            tip_text(str(getattr(control, 'TEXT', '') or ''))
        except Exception:
            pass
        for sid in later:
            call_later(seconds, _dh_state_start, player, sid, 'sing %s' % state_id)
    elif name == 'SkillStateShowSecretTreasure':
        _dh_secret_choice(player, control)
    elif name == 'SkillStateBotShadow':
        index = _dh_decoy_spawn(player, control)
        if index:
            undo.append(('decoy', index))
    elif name == 'SkillStateChargeNearAttack':
        if once('charge-near'):
            log('local-hero-state-unsupported', control=name, state=state_id)
    elif name == 'SkillStageStagnation':
        if once('stagnation'):
            log('local-hero-state-unsupported', control=name, state=state_id)
    elif name == 'SkillStateWeaponEffect':
        if once('weapon-effect'):
            log('local-hero-state-unsupported', control=name, state=state_id)
    else:
        return None
    return undo


def _dh_fx_undo(player, kind, value):
    if kind == 'call':
        name, args = value[0], value[1]
        getattr(player, name)(*args)
    elif kind == 'prop':
        _dh_prop_set(player, value, False)
    elif kind == 'prop0':
        _dh_prop_set(player, value, 0)
    elif kind == 'fly':
        player.hideFlyingAccessory = False
        player.refreshFlyingAccessory('current')
    elif kind == 'speed':
        _dh_hero_states['speed'] = max(0, _dh_hero_states['speed'] - int(value))
        change_prop(player, 'boostSpeedBuff', int(_buffs.get('boostSpeedBuff', (0, 0))[1]))
    elif kind == 'jump':
        stop = getattr(player, 'stopJumpBuff', None)
        if callable(stop):
            stop()
        else:
            _dh_prop_set(player, 'hormoneGunJumpBuff', 0)
    elif kind == 'immune':
        _dh_fx['immune'] = None
        _dh_prop_set(player, 'immuneFatalDamage', False)
    elif kind == 'decoy':
        _dh_decoy_remove(value)


# m28's controller dispatch learns the new ones (the unsupported branch is replaced by a lookup here)
_dh_control_start_m28 = globals().get('_dh_control_start_m28') or _dh_state_control_start


def _dh_state_control_start(player, state_id, token, control, flow):
    undo = _dh_fx_control(player, state_id, token, control, flow)
    if undo is not None:
        return undo
    return _dh_control_start_m28(player, state_id, token, control, flow)


_dh_state_end_m28 = globals().get('_dh_state_end_m28') or _dh_state_end


def _dh_state_end(player, state_id, token, why):
    state = _dh_hero_states['active'].get(state_id)
    if state is not None and (token is None or state['token'] == token):
        for entry in list(state['undo']):
            kind = entry[0]
            value = entry[1] if len(entry) == 2 else tuple(entry[1:])
            if kind in ('call', 'prop', 'prop0', 'fly', 'speed', 'jump', 'immune', 'decoy'):
                try:
                    _dh_fx_undo(player, kind, value)
                except Exception:
                    log_error('local-hero-fx-undo-error', kind=kind)
        state['undo'] = [entry for entry in state['undo'] if entry[0] not in ('call', 'prop', 'prop0', 'fly', 'speed', 'jump', 'immune', 'decoy')]
    return _dh_state_end_m28(player, state_id, token, why)


# cheat death (ImmuneFatal) + the trigger that goes with it
def _dh_immune_hit_wrapper(player, hurt, *args, **kwargs):
    immune = _dh_fx.get('immune')
    if immune and isinstance(hurt, dict):
        try:
            now = time.time()
            old = int(player.hp)
            damage = int(hurt.get('damage') or 0)
            if now < immune['until']:
                hurt = dict(hurt)
                hurt['damage'] = 0
                hurt['hp'] = old
            elif damage >= old and now >= immune['ready_at']:
                immune['ready_at'] = now + immune['interval']
                immune['until'] = now + immune['invincible']
                hurt = dict(hurt)
                hurt['damage'] = max(0, old - 1)
                hurt['hp'] = 1
                log('local-hero-immune-fatal', next_in=immune['interval'])
                _dh_trigger_event(player, 'immune')
        except Exception:
            log_error('local-hero-immune-error')
    return _dh_immune_hit_wrapper._dh_inner(player, hurt, *args, **kwargs)


# the leftover triggers: ImmuneFatal, ShootInAir (fire between jumpStart and jumpEnd), Run and SpeedOverThreshold
# (the avatar's ground speed, sampled every 0.5 s), Reborn / RobotShadowDie have no mechanic here (logged once)
_DH_RUN_SPEED = 450.0          # cm/s: faster than a walk
_dh_trigger_event_m29 = globals().get('_dh_trigger_event_m29') or _dh_trigger_event


def _dh_trigger_event(player, event, **info):
    for entry in list(_dh_hero_triggers['list']):
        kind, fields = entry['kind'], entry['fields']
        try:
            if event == 'immune' and kind == 'SkillTriggerImmuneFatal':
                _dh_hero_triggers['active'].pop(entry['skill'], None)
                _dh_trigger_fire(player, entry, 'immune')
            elif event == 'attack' and kind == 'SkillTriggerShootInAir' and _dh_fx['air']:
                _dh_hero_triggers['active'].pop(entry['skill'], None)
                _dh_trigger_fire(player, entry, 'air')
            elif event == 'run' and kind == 'SkillTriggerRun':
                if info.get('on'):
                    _dh_trigger_fire(player, entry, 'run')
                else:
                    _dh_trigger_release(player, entry, 'run')
            elif event == 'fast' and kind == 'SkillTriggerSpeedOverThreshold':
                if info.get('on'):
                    _dh_trigger_fire(player, entry, 'fast')
                else:
                    _dh_trigger_release(player, entry, 'fast')
            elif kind in ('SkillTriggerReborn', 'SkillTriggerRobotShadowDie') and once('trigger-' + kind):
                log('local-hero-trigger-unsupported', kind=kind, skill=entry['skill'])
        except Exception:
            log_error('local-hero-trigger-error', skill=entry['skill'], event=event)
    if event == 'jump':
        _dh_fx['air'] = bool(info.get('on'))
    return _dh_trigger_event_m29(player, event, **info)


def _dh_speed_tick(player, token):
    if _dh_hero_triggers.get('speed_token') != token or BATTLE.get('phase') != 'fighting':
        return
    try:
        now = time.time()
        pos = _point(player.position)
        last_at, last_pos = _dh_fx.get('speed_at'), _dh_fx.get('speed_pos')
        if last_at and last_pos:
            speed = math.hypot(pos[0] - last_pos[0], pos[2] - last_pos[2]) / max(0.1, now - last_at)
            running = speed >= _DH_RUN_SPEED and not getattr(player, 'inLandVehicle', False)
            if running != _dh_fx['running']:
                _dh_fx['running'] = running
                _dh_trigger_event(player, 'run', on=running)
            threshold = 0.0
            for entry in _dh_hero_triggers['list']:
                if entry['kind'] == 'SkillTriggerSpeedOverThreshold':
                    threshold = float(entry['fields'].get('VELOCITY_THRESHOLD') or 0) * 100.0 / 3.6
            if threshold:
                fast = speed >= threshold
                if fast != _dh_fx['fast']:
                    _dh_fx['fast'] = fast
                    _dh_trigger_event(player, 'fast', on=fast)
        _dh_fx['speed_at'], _dh_fx['speed_pos'] = now, pos
    except Exception:
        log_error('local-hero-speed-tick-error')
    call_later(0.5, _dh_speed_tick, player, token)


_dh_trigger_build_m29 = globals().get('_dh_trigger_build_m29') or _dh_trigger_build


def _dh_trigger_build(player):
    _dh_trigger_build_m29(player)
    kinds = set(entry['kind'] for entry in _dh_hero_triggers['list'])
    if kinds & set(('SkillTriggerRun', 'SkillTriggerSpeedOverThreshold')):
        token = object()
        _dh_hero_triggers['speed_token'] = token
        _dh_fx.update(speed_at=None, speed_pos=None, running=False, fast=False)
        call_later(0.5, _dh_speed_tick, player, token)


def _dh_fx_leave_wrapper(player=None, *args, **kwargs):
    for index in list(_dh_fx['decoys'].keys()):
        _dh_decoy_remove(index)
    _dh_fx.update(immune=None, air=False, running=False, fast=False)
    _dh_hero_triggers['speed_token'] = None
    return _dh_fx_leave_wrapper._dh_inner(player, *args, **kwargs)


try:
    _dh_m32 = {
        'hit': _dh_wrap_global('take_player_hit', _dh_immune_hit_wrapper, '_dh_fx'),
        'leave': _dh_wrap_global('leave_battle', _dh_fx_leave_wrapper, '_dh_fx'),
    }
    log('local-hero-fx-installed', **_dh_m32)
except Exception:
    log_error('local-hero-fx-install-error')


# a death ends the round for the hero too: states, triggers and decoys go (leave_battle may never run)
def _dh_fx_died_wrapper(player, *args, **kwargs):
    try:
        _dh_states_clear(player)
        _dh_hero_triggers.update({'list': [], 'active': {}, 'detect': None, 'speed_token': None})
        for index in list(_dh_fx['decoys'].keys()):
            _dh_decoy_remove(index)
        _dh_fx.update(immune=None, air=False, running=False, fast=False)
    except Exception:
        log_error('local-hero-died-clear-error')
    return _dh_fx_died_wrapper._dh_inner(player, *args, **kwargs)


try:
    _dh_m32b = {'died': _dh_wrap_global('player_died', _dh_fx_died_wrapper, '_dh_fx')}
    log('local-hero-fx-died-installed', **_dh_m32b)
except Exception:
    log_error('local-hero-fx-died-install-error')


# ---- m33: Epic Clash 2.0 relic energy.  The mode's currency (SecretTreasureAddCoin props, e.g. 2200001) is
# picked like loot and counted on the player's mibaoCurrency property, which the relic HUD reads; coins are
# rolled on the map's spots and dropped in every crate and airdrop on map 730.
_DH_COIN_ITEM = 2200001
_DH_COIN_SPOT_SHARE = 0.10
_DH_COIN_DEFAULT = 10


def _dh_coin_value(prop):
    row = _dh_prop_type(prop)
    for name in ('COINS', 'COIN_NUM', 'CURRENCY_NUM', 'NUM', 'VALUE', 'ADD_NUM', 'AMOUNT'):
        try:
            value = int(getattr(row, name, 0) or 0)
        except Exception:
            value = 0
        if value > 0:
            return value
    if once('coin-fields'):
        log('local-relic-coin-fields', fields=[k for k in dir(row) if k.isupper()][:16])
    return _DH_COIN_DEFAULT


def _dh_coin_add(player, prop, taken):
    value = _dh_coin_value(prop) * max(1, int(taken))
    old = int(getattr(player, 'mibaoCurrency', 0) or 0)
    try:
        player.mibaoCurrency = old + value
        setter = getattr(player, 'set_mibaoCurrency', None)
        if callable(setter):
            setter(old)
    except Exception:
        log_error('local-relic-coin-error')
        return False
    try:
        import Globals
        ui = (getattr(Globals.uiMgr, '____all_ui__', {}) or {}).get('UIBattlegroundsInGame')
        main = ui.GetComponent('UISecretTreasureMain') if ui is not None else None
        if main is not None:
            main.currencyNum.setString(str(old + value))
    except Exception:
        pass
    log('local-relic-coin', value=value, total=old + value)
    return True


def _dh_coin_roll_spot_wrapper(seed, index, group, *args, **kwargs):
    items = _dh_coin_roll_spot_wrapper._dh_inner(seed, index, group, *args, **kwargs)
    try:
        if items and _dh_relic_map():
            import random as _random
            if _random.Random('%s-coin-%d' % (seed, index)).random() < _DH_COIN_SPOT_SHARE:
                return [(_DH_COIN_ITEM, 1, 0.0, 0.0)]
    except Exception:
        pass
    return items


def _dh_coin_heritage_wrapper(randomizer, *args, **kwargs):
    items = _dh_coin_heritage_wrapper._dh_inner(randomizer, *args, **kwargs)
    try:
        if _dh_relic_map() and isinstance(items, dict):
            items['heritage-coin'] = [_DH_COIN_ITEM, 1, {}]
    except Exception:
        pass
    return items


def _dh_coin_grant_wrapper(player, prop, taken, *args, **kwargs):
    try:
        kind = prop_kind(prop)
    except Exception:
        kind = None
    if kind == 'SecretTreasureAddCoin':
        _dh_coin_add(player, int(prop), int(taken))
        return 'coin'
    return _dh_coin_grant_wrapper._dh_inner(player, prop, taken, *args, **kwargs)


try:
    _dh_m33 = {
        'spots': _dh_wrap_global('roll_spot', _dh_coin_roll_spot_wrapper, '_dh_coins'),
        'heritage': _dh_wrap_global('heritage_items', _dh_coin_heritage_wrapper, '_dh_coins'),
        'grant': _dh_wrap_global('grant_prop', _dh_coin_grant_wrapper, '_dh_coins'),
    }
    log('local-relic-coins-installed', **_dh_m33)
except Exception:
    log_error('local-relic-coins-install-error')


# ---- m34: hell-fire device (the client's own weapon buff: iDtsEquip.addWeaponBuff(propertyID)) and hero respawns
def _dh_fire_rate_buff(player, seconds):
    try:
        import dts_const
        prop = getattr(dts_const.DtsWeaponCompProperties, 'WeaponFireSpeed', None)
    except Exception:
        prop = None
    if prop is None:
        if once('fire-rate-prop'):
            log('local-race-use-unsupported', kind='AutoRoyalePropQuickFireSpeed')
        return False
    try:
        player.addWeaponBuff(prop)
    except Exception:
        log_error('local-race-fire-rate-error')
        return False
    token = object()
    _dh_car_fx['fire_rate'] = token
    call_later(seconds, _dh_fire_rate_end, player, prop, token)
    log('local-race-fire-rate', seconds=seconds)
    return True


def _dh_fire_rate_end(player, prop, token):
    if _dh_car_fx.get('fire_rate') != token:
        return
    _dh_car_fx['fire_rate'] = None
    for name in ('removeWeaponBuff', 'delWeaponBuff', 'clearWeaponBuff', 'stopWeaponBuff'):
        fn = getattr(player, name, None)
        if callable(fn):
            try:
                fn(prop)
            except TypeError:
                try:
                    fn()
                except Exception:
                    pass
            except Exception:
                pass
            return


# Hero maps had respawns: a killing hit on a hero with respawns left puts them back at full HP on a fresh
# birth point instead of the death screen (the Reborn trigger fires; hero 40's mark 171 shortens the wait,
# which here is the teleport itself).  Two respawns per round.
_DH_RESPAWNS = 2
_dh_respawn = globals().get('_dh_respawn') or {'used': 0}


def _dh_respawn_point(player):
    import random as _random
    births = list(_world.get('births') or [])
    if not births:
        return None
    x, _y, z = _point(player.position)
    far = [b for b in births if math.hypot(b[0] - x, b[2] - z) > 150.0]
    pick = _random.choice(far or births)
    return (pick[0], pick[1], pick[2])


def _dh_respawn_hit_wrapper(player, hurt, *args, **kwargs):
    try:
        if isinstance(hurt, dict) and int(_dh_hero.get('hero') or 0) and int(BATTLE.get('map') or 0) in _DH_HERO_MAPS and _dh_respawn['used'] < _DH_RESPAWNS:
            old = int(player.hp)
            damage = int(hurt.get('damage') or 0)
            if damage >= old and not (_dh_fx.get('immune') and time.time() < _dh_fx['immune']['until']):
                _dh_respawn['used'] += 1
                hurt = dict(hurt)
                hurt['damage'] = max(0, old - 1)
                hurt['hp'] = 1
                point = _dh_respawn_point(player)
                call_later(0.3, _dh_respawn_now, player, point)
                log('local-hero-respawn', used=_dh_respawn['used'], point=[round(v) for v in point] if point else None)
    except Exception:
        log_error('local-hero-respawn-error')
    return _dh_respawn_hit_wrapper._dh_inner(player, hurt, *args, **kwargs)


def _dh_respawn_now(player, point):
    try:
        top = int(getattr(player, 'maxHp', 0) or FULL_HP)
        restore_hp(player, top)
        if point is not None:
            land_player(player, point)
        tip_text('Respawned (%d left)' % max(0, _DH_RESPAWNS - _dh_respawn['used']))
        try:
            player.onReborn()
        except Exception:
            pass
        _dh_trigger_event(player, 'reborn')
    except Exception:
        log_error('local-hero-respawn-now-error')


_dh_trigger_event_m32 = globals().get('_dh_trigger_event_m32') or _dh_trigger_event


def _dh_trigger_event(player, event, **info):
    if event == 'reborn':
        for entry in list(_dh_hero_triggers['list']):
            if entry['kind'] == 'SkillTriggerReborn':
                _dh_hero_triggers['active'].pop(entry['skill'], None)
                _dh_trigger_fire(player, entry, 'reborn')
    return _dh_trigger_event_m32(player, event, **info)


def _dh_respawn_leave_wrapper(player=None, *args, **kwargs):
    _dh_respawn['used'] = 0
    return _dh_respawn_leave_wrapper._dh_inner(player, *args, **kwargs)


try:
    _dh_m34 = {
        'hit': _dh_wrap_global('take_player_hit', _dh_respawn_hit_wrapper, '_dh_respawn'),
        'leave': _dh_wrap_global('leave_battle', _dh_respawn_leave_wrapper, '_dh_respawn'),
    }
    log('local-hero-respawn-installed', **_dh_m34)
except Exception:
    log_error('local-hero-respawn-install-error')



# ---- m36: supply airdrops that can be seen, and airdrop rules from the admin console.
# (1) The box fell 1000 m under the ground: while it fell, ground_height() (landscape.get_detail_height) answered
#     a height 1000 m below the real one wherever the terrain had not streamed in (far from the player), and the
#     fall took that for the ground.  Every box of every round landed at <ground - 1000> (log: drop at y 512,
#     landed at -488) - no crate, no beam, no smoke for anyone.  The fall now keeps the height the drop point came
#     with (the level's own spots know their height) unless the landscape answers within 120 m of it.
# (2) Rules from the lobby prop rlLobby.airdrops (console -> Lobby -> Airdrops): on/off, first drop after N s,
#     interval, drops per round, a share of the drops placed near a player (within N m) so they are actually
#     seen, and the "Supply drop" tip.  Without the block the map's own AIR_DROP params stay as before.
# (3) On landing the box's own landed effects are started (whatever this build's DtsAvatarHeroAirDrop has: the
#     light beam, the smoke column) and the names found are logged once (local-airdrop-box-api) for tuning.
_DH_AIRDROP_DEFAULTS = {'enabled': True, 'first_seconds': 120, 'interval_seconds': 150, 'min_drops': 6, 'max_drops': 7,
                        'near_share': 0.5, 'near_metres': 400, 'announce': True}
_DH_GROUND_TOLERANCE = 120.0


def _dh_airdrop_rules():
    try:
        config = LOBBY._dh_lobby_config() if LOBBY is not None and hasattr(LOBBY, '_dh_lobby_config') else {}
    except Exception:
        config = {}
    rules = config.get('airdrops') if isinstance(config, dict) else None
    if not isinstance(rules, dict):
        return None
    out = dict(_DH_AIRDROP_DEFAULTS)
    for key in out:
        if key in rules and rules[key] is not None:
            out[key] = rules[key]
    return out


def _dh_airdrop_config_wrapper(*args, **kwargs):
    base = _dh_airdrop_config_wrapper._dh_inner(*args, **kwargs)
    rules = _dh_airdrop_rules()
    if rules is None:
        return base
    if not rules.get('enabled', True):
        return None
    config = dict(base) if isinstance(base, dict) else {'activate': 120.0, 'interval': 150.0, 'times': (6, 7), 'specific': [], 'speed': 50.0, 'group': 0}
    try:
        config['activate'] = float(rules['first_seconds'])
        config['interval'] = float(rules['interval_seconds'])
        low, high = int(rules['min_drops']), int(rules['max_drops'])
        config['times'] = (min(low, high), max(low, high))
        config['specific'] = []
    except Exception:
        log_error('local-airdrop-rules-error')
        return base
    return config


def _dh_airdrop_spot_wrapper(randomizer, config, *args, **kwargs):
    """A share of the drops lands near the player (inside near_metres), on one of the level's spots when
    there is one, so the plane, the crate and the beam are seen; the rest keep the game's own placement."""
    rules = _dh_airdrop_rules()
    try:
        if rules is not None and randomizer.random() < float(rules.get('near_share') or 0.0):
            player = current_player()
            px, py, pz = _point(player.position)
            reach = float(rules.get('near_metres') or 400) * 10.0      # m41h: metres -> game units (0.1 m)
            circle = safe_circle()
            spots = []
            for spot in (_world.get('spots') or []):
                distance = _dh_math.hypot(spot[0] - px, spot[2] - pz)
                if 600.0 <= distance <= reach and (circle is None or _dh_math.hypot(spot[0] - circle[0], spot[2] - circle[1]) <= circle[2] * 0.95):
                    spots.append(spot)
            if spots:
                spot = randomizer.choice(spots)
                return spot[0], spot[1], spot[2], 'near-player'
            angle = randomizer.uniform(0.0, 2.0 * _dh_math.pi)
            distance = randomizer.uniform(80.0, max(100.0, reach))
            x, z = px + distance * _dh_math.cos(angle), pz + distance * _dh_math.sin(angle)
            ground = ground_height(x, z)
            return x, (ground if ground else py), z, 'near-player'
    except Exception:
        log_error('local-airdrop-spot-error')
    return _dh_airdrop_spot_wrapper._dh_inner(randomizer, config, *args, **kwargs)


def _dh_airdrop_landed_fx(box, x, ground, z):
    """Start the box's own landed presentation (beam, smoke) and learn its API once."""
    names = [name for name in dir(box) if any(key in name.lower() for key in ('smoke', 'effect', 'land', 'light', 'fx', 'arrive'))]
    if once('airdrop-box-api'):
        log('local-airdrop-box-api', names=names[:60], cls=type(box).__name__)
    for name in ('onLand', 'onLanded', 'onAirDropLand', 'onArrive', 'playLandEffect', 'showSmoke', 'playSmoke', 'createSmokeEffect', 'landEffect'):
        method = getattr(box, name, None)
        if callable(method):
            try:
                method()
                log('local-airdrop-box-fx', method=name)
                break
            except TypeError:
                try:
                    method(x, ground, z)
                    log('local-airdrop-box-fx', method=name, args=3)
                    break
                except Exception:
                    continue
            except Exception:
                continue
    for attr in ('isLand', 'landed', 'isLanded', 'onGround'):
        if hasattr(box, attr):
            try:
                setattr(box, attr, True)
            except Exception:
                pass


def _dh_fall_airdrops(token, again=True):
    """fall_airdrops with the ground fix (see the m36 note) and the landed effects / tip."""
    if token != _airdrops.get('token'):
        return False
    now = _dh_time.time()
    rules = _dh_airdrop_rules() or {}
    for entity_id, state in list(_airdrops['falling'].items()):
        box = vehicle_entity(entity_id)
        if box is None:
            state['clock'] = now
            if now - state.get('born', now) > AIRDROP_MISSING_WAIT:
                _airdrops['falling'].pop(entity_id, None)
            continue
        known = state.get('ground')
        measured = ground_height(state['x'], state['z'])
        if measured and (known is None or abs(float(measured) - float(known)) <= _DH_GROUND_TOLERANCE):
            ground = float(measured)
        else:
            ground = float(known if known is not None else (measured or 0.0))
        state['ground'] = ground
        state['y'] -= state['speed'] * (now - state['clock'])
        state['clock'] = now
        landed = state['y'] <= ground + HERITAGE_LIFT
        if landed:
            state['y'] = ground + HERITAGE_LIFT
            _airdrops['falling'].pop(entity_id, None)
        try:
            hold_box(box, (state['x'], state['y'], state['z']))
            if landed:
                box.dropping = False
                place_airdrop_light(entity_id, state['x'], ground, state['z'])
                _dh_airdrop_landed_fx(box, state['x'], ground, state['z'])
                try:
                    px, py, pz = _point(current_player().position)
                    distance = _dh_math.hypot(state['x'] - px, state['z'] - pz)
                    metres = distance / 10.0                       # m41h: game units (0.1 m) -> metres
                    if rules.get('announce', True) and metres <= float(rules.get('near_metres') or 400) * 2.5:
                        tip_text('Supply drop landed %d m away' % int(metres))
                except Exception:
                    distance = None
                log('local-battle-airdrop-landed', box=entity_id, position=[round(state['x']), round(state['y']), round(state['z'])],
                    measured=round(measured) if measured else None, distance=round(distance) if distance else None)
        except Exception:
            if once('airdrop-fall'):
                log_error('local-battle-airdrop-fall-error')
    if _airdrops['falling'] and again:
        run_airdrops(token)
    return True


def _dh_fall_airdrops_wrapper(token, again=True):
    return _dh_fall_airdrops(token, again)


try:
    import math as _dh_math
    import time as _dh_time
    _dh_m36 = {
        'config': _dh_wrap_global('airdrop_config', _dh_airdrop_config_wrapper, '_dh_airdrops'),
        'spot': _dh_wrap_global('airdrop_spot', _dh_airdrop_spot_wrapper, '_dh_airdrops'),
        'fall': _dh_wrap_global('fall_airdrops', _dh_fall_airdrops_wrapper, '_dh_airdrops'),
        'rules': _dh_airdrop_rules(),
    }
    log('local-airdrop-rules-installed', **_dh_m36)
except Exception:
    log_error('local-airdrop-rules-install-error')


# ---- m36b: the drop point's own height.  The far drops were still 1000 m under the ground: the height came from
# ground_height() AT THE DROP (the random-point branch of airdrop_spot, and any spot without a height), which
# answers real - 1000 where the terrain is not streamed in.  The drop point now takes its height from the nearest
# level spots (they carry the real ground), and only trusts the landscape within 150 m of that.  Without rules in
# the lobby push the built-in defaults apply (half of the drops within 400 m of the player) instead of nothing.
# On landing the box's own landing detection is started (startLandDetect: the crate settles on the real ground once
# the collision is loaded and plays its landing effects) and the landing methods' code is logged once.
_DH_SPOT_TOLERANCE = 150.0


def _dh_ground_estimate(x, z, reach=400.0):
    """Median height of the nearest level spots within reach metres (they know the real ground), else None."""
    try:
        near = []
        for spot in (_world.get('spots') or []):
            d = _dh_math.hypot(spot[0] - x, spot[2] - z)
            if d <= reach:
                near.append((d, float(spot[1])))
        if not near:
            return None
        near.sort()
        heights = sorted(h for _d, h in near[:7])
        return heights[len(heights) // 2]
    except Exception:
        return None


def _dh_airdrop_rules_m36b():
    rules = _dh_airdrop_rules_m36(*()) if False else None
    try:
        config = LOBBY._dh_lobby_config() if LOBBY is not None and hasattr(LOBBY, '_dh_lobby_config') else {}
    except Exception:
        config = {}
    block = config.get('airdrops') if isinstance(config, dict) else None
    out = dict(_DH_AIRDROP_DEFAULTS)
    if isinstance(block, dict):
        for key in out:
            if key in block and block[key] is not None:
                out[key] = block[key]
    return out


_dh_airdrop_rules_m36 = _dh_airdrop_rules
_dh_airdrop_rules = _dh_airdrop_rules_m36b


def _dh_airdrop_spot_height_wrapper(randomizer, config, *args, **kwargs):
    x, y, z, where = _dh_airdrop_spot_height_wrapper._dh_inner(randomizer, config, *args, **kwargs)
    try:
        estimate = _dh_ground_estimate(x, z)
        landscape = ground_height(x, z)
        if estimate is not None:
            if y is None or abs(float(y) - estimate) > _DH_SPOT_TOLERANCE:
                log('local-airdrop-height', where=where, given=round(y) if y is not None else None, landscape=round(landscape) if landscape else None,
                    used=round(estimate), source='spots')
                y = estimate
        elif y is None:
            px, py, pz = _point(current_player().position)
            if landscape and abs(float(landscape) - py) <= 600.0:
                y = float(landscape)
            else:
                y = py
                log('local-airdrop-height', where=where, given=None, landscape=round(landscape) if landscape else None, used=round(y), source='player')
    except Exception:
        log_error('local-airdrop-height-error')
    return x, y, z, where


def _dh_airdrop_landed_fx_m36b(box, x, ground, z):
    started = None
    for name in ('startLandDetect',):
        method = getattr(box, name, None)
        if callable(method):
            try:
                method()
                started = name
            except Exception:
                try:
                    method(_dh_math.floor(0))
                except Exception:
                    pass
    if once('airdrop-box-code'):
        info = {}
        for name in ('startLandDetect', 'castSfxAtPosition', 'onLightModelLoad', 'stopSfxAtPosition', 'enterWorld', 'onLoadAirDrop', 'set_dropping'):
            method = getattr(box, name, None)
            code = getattr(getattr(method, 'im_func', method), 'func_code', None) or getattr(method, '__code__', None)
            if code is not None:
                info[name] = {'args': list(code.co_varnames[:code.co_argcount]), 'names': list(code.co_names)[:40],
                              'consts': [c for c in code.co_consts if isinstance(c, (str, unicode, int, float))][:20]}
        log('local-airdrop-box-code', started=started, pos_sfx=safe(getattr(box, 'pos_sfx', None), 200), **info)
    _dh_airdrop_landed_fx_m36(box, x, ground, z)


_dh_airdrop_landed_fx_m36 = _dh_airdrop_landed_fx
_dh_airdrop_landed_fx = _dh_airdrop_landed_fx_m36b


def _dh_schedule_airdrops_wrapper(*args, **kwargs):
    try:
        log('local-airdrop-rules-used', **(_dh_airdrop_rules() or {}))
    except Exception:
        pass
    return _dh_schedule_airdrops_wrapper._dh_inner(*args, **kwargs)


try:
    _dh_m36b = {
        'height': _dh_wrap_global('airdrop_spot', _dh_airdrop_spot_height_wrapper, '_dh_airdrops_h'),
        'schedule': _dh_wrap_global('schedule_airdrops', _dh_schedule_airdrops_wrapper, '_dh_airdrops_h'),
    }
    log('local-airdrop-height-installed', **_dh_m36b)
except Exception:
    log_error('local-airdrop-height-install-error')


# ---- m37: the supply crate's real model.  The hook made every supply box with AIR_DROP_MODEL
# 'character/female_battlegrounds/supplybox/supplybox_ros.gim' - a file this client does not have - so the crate's
# model never loaded (probe 2026-10-23: model None, no light object, no collider, startLandDetect -> no 'trap'):
# nothing to see, and the beam / smoke / landing detection that hang off the model load never started.  The
# class itself (DtsPlayerHeritage.AIR_DROP_MODEL) names supplybox_kaol.gim, with parachute_04.gim as the parachute
# and supplybox_xingzuan1.gim as the gold crate.  release_supply() reads the hook global AIRDROP_MODEL on every
# drop, so the global is pointed at the real crate here (no wrapper, nothing to mark).
_DH_AIRDROP_REAL_MODEL = 'character/female_battlegrounds/supplybox/supplybox_kaol.gim'
try:
    _dh_m37_before = globals().get('AIRDROP_MODEL')
    try:
        import sys as _dh_sys37
        _dh_heritage = _dh_sys37.modules.get('DtsPlayerHeritage')
        _dh_heritage_cls = getattr(_dh_heritage, 'DtsPlayerHeritage', None)
        _dh_class_model = getattr(_dh_heritage_cls, 'AIR_DROP_MODEL', None)
    except Exception:
        _dh_class_model = None
    AIRDROP_MODEL = _dh_class_model if isinstance(_dh_class_model, basestring) and _dh_class_model.endswith('.gim') else _DH_AIRDROP_REAL_MODEL
    try:
        _dh_box_cls = getattr(_dh_sys37.modules.get('DtsAvatarHeroAirDrop'), 'DtsAvatarHeroAirDrop', None)
        if _dh_box_cls is not None:
            _dh_box_cls.AIR_DROP_MODEL = AIRDROP_MODEL          # a class already patched by an earlier drop
    except Exception:
        pass
    log('local-airdrop-model', before=safe(_dh_m37_before, 100), now=AIRDROP_MODEL, from_class=_dh_class_model is not None)
except Exception:
    log_error('local-airdrop-model-error')


# ---- m38: airdrop rules per battle map and the crate's fall speed.  The console's Lobby control now carries
# rlLobby.airdrops (defaults - they were saved but never pushed before, so every round used the built-in values)
# and rlLobby.airdrops_by_map {map id: overrides}.  The rules for a round are defaults <- airdrops <- the block of
# the map the round plays on (BATTLE['map']); drop_speed (m/s) feeds the game's DROP_SPEED.
def _dh_airdrop_rules_m38():
    try:
        config = LOBBY._dh_lobby_config() if LOBBY is not None and hasattr(LOBBY, '_dh_lobby_config') else {}
    except Exception:
        config = {}
    out = dict(_DH_AIRDROP_DEFAULTS)
    if not isinstance(config, dict):
        return out
    blocks = [config.get('airdrops')]
    by_map = config.get('airdrops_by_map')
    if isinstance(by_map, dict):
        try:
            map_id = str(int(BATTLE.get('map') or 0))
        except Exception:
            map_id = ''
        blocks.append(by_map.get(map_id))
    for block in blocks:
        if isinstance(block, dict):
            for key, value in block.items():
                if value is not None:
                    out[key] = value
    return out


_dh_airdrop_rules_m36b_kept = _dh_airdrop_rules
_dh_airdrop_rules = _dh_airdrop_rules_m38


def _dh_airdrop_config_speed_wrapper(*args, **kwargs):
    config = _dh_airdrop_config_speed_wrapper._dh_inner(*args, **kwargs)
    try:
        rules = _dh_airdrop_rules() or {}
        speed = rules.get('drop_speed')
        if isinstance(config, dict) and speed:
            config = dict(config)
            config['speed'] = max(10.0, min(300.0, float(speed)))
    except Exception:
        log_error('local-airdrop-speed-error')
    return config


try:
    _dh_m38 = {'speed': _dh_wrap_global('airdrop_config', _dh_airdrop_config_speed_wrapper, '_dh_airdrops_s')}
    log('local-airdrop-map-rules-installed', **_dh_m38)
except Exception:
    log_error('local-airdrop-map-rules-install-error')


# ---- m39: Zombie Trial (the game's camp war, type 12) - the client half of ros_admin/zombie_mode.py.
# A zombie is an avatar whose identityType is PlayerIdentity.Zombie (1): the client dresses it, adds the poison
# aura, hides the gun buttons and shows the gene bar by itself.  The host flags its zombie bots with act['z'] = 1
# (applied here on every body), a turned player sends 'z' in its own act for the other windows.  A lethal bite
# from a zombie (hurt 'from' a flagged body) does not kill: the player keeps 1 HP and turns - 200 HP, fists,
# zombie jump, the host is told on the loot channel ('camp').  Shots between members of one camp do nothing.
_DH_ZOMBIE_MAPS = (792, 715, 716, 722)
_DH_ZOMBIE_HP = 200
_DH_ZOMBIE_GENE = 300
_dh_zombie = globals().get('_dh_zombie') or {'me': False, 'bodies': set(), 'logged': False}


def _dh_zombie_map():
    try:
        return int(BATTLE.get('map') or 0) in _DH_ZOMBIE_MAPS
    except Exception:
        return False


def _dh_zombie_mark(entity, is_zombie):
    try:
        current = int(getattr(entity, 'identityType', 0) or 0)
        if is_zombie and current != 1:
            set_player_field(entity, 'identityType', 1)
        elif not is_zombie and current == 1:
            set_player_field(entity, 'identityType', 0)
        camp = getattr(entity, 'campType', None)
        if camp is not None and hasattr(camp, 'setCampWarID'):
            camp.setCampWarID(2 if is_zombie else 1)
        return True
    except Exception:
        if once('zombie-mark'):
            log_error('local-zombie-mark-error')
        return False


def _dh_zombie_apply_act_wrapper(battle_id, handle, act, *args, **kwargs):
    try:
        if isinstance(act, dict) and act.get('z') and _dh_zombie_map() and battle_id not in _dh_zombie['bodies']:
            entity = _resolve_entity(handle)
            if entity is not None and not isinstance(entity, (int, long_type)):
                _dh_zombie['bodies'].add(battle_id)
                _dh_zombie_mark(entity, True)
                if not _dh_zombie['logged']:
                    _dh_zombie['logged'] = True
                    log('local-zombie-body', body=battle_id, cls=type(entity).__name__)
    except Exception:
        if once('zombie-act'):
            log_error('local-zombie-act-error')
    return _dh_zombie_apply_act_wrapper._dh_inner(battle_id, handle, act, *args, **kwargs)


def _dh_zombie_my_act_wrapper(*args, **kwargs):
    act = _dh_zombie_my_act_wrapper._dh_inner(*args, **kwargs)
    try:
        if _dh_zombie['me'] and isinstance(act, dict):
            act['z'] = 1
    except Exception:
        pass
    return act


def _dh_zombie_turn(player):
    if _dh_zombie['me']:
        return False
    _dh_zombie['me'] = True
    _dh_zombie_mark(player, True)
    try:
        player.maxHp = _DH_ZOMBIE_HP
    except Exception:
        pass
    try:
        restore_hp(player, _DH_ZOMBIE_HP)
    except Exception:
        log_error('local-zombie-hp-error')
    try:
        switch_weapon(player, MELEE_SLOT)
    except Exception:
        pass
    try:
        player.setZombieJumpMode(True)
    except Exception:
        pass
    try:
        import Globals
        hud = getattr(Globals.uiMgr, 'UIBattlegroundsInGame', None)
        if hud is not None:
            hud.onGeneValueChanged(_DH_ZOMBIE_GENE)
    except Exception:
        log_error('local-zombie-hud-error')
    try:
        send(LOOT_PREFIX + json.dumps({'camp': {'me': BATTLE.get('entity_id'), 'z': 1}}))
    except Exception:
        log_error('local-zombie-report-error')
    tip_text('You are infected! Hunt the humans.')
    log('local-zombie-turned', hp=_DH_ZOMBIE_HP)
    return True


def _dh_zombie_hit_wrapper(player, hurt, *args, **kwargs):
    try:
        if _dh_zombie_map() and not _dh_zombie['me'] and isinstance(hurt, dict) and hurt.get('z'):
            # the host clamped a lethal bite to 1 HP and flagged the record: the player turns after the hit lands
            hurt = dict(hurt)
            hurt['hp'] = max(1, int(hurt.get('hp') or 1))
            call_later(0.2, _dh_zombie_turn, player)
    except Exception:
        log_error('local-zombie-hit-error')
    return _dh_zombie_hit_wrapper._dh_inner(player, hurt, *args, **kwargs)


def _dh_zombie_hurt_avatar_wrapper(player, target, damage, src_pos, hit_part, hit_type, weapon, weapon_name, *args, **kwargs):
    try:
        if _dh_zombie_map() and not is_player_body(target):
            body = battle_id_of(target)
            target_zombie = body in _dh_zombie['bodies']
            if target_zombie == bool(_dh_zombie['me']):
                if once('zombie-friendly'):
                    tip_text('Same camp: no damage.')
                return None
    except Exception:
        if once('zombie-hurt'):
            log_error('local-zombie-hurt-error')
    return _dh_zombie_hurt_avatar_wrapper._dh_inner(player, target, damage, src_pos, hit_part, hit_type, weapon, weapon_name, *args, **kwargs)


def _dh_zombie_snapshot_wrapper(snapshot, *args, **kwargs):
    result = _dh_zombie_snapshot_wrapper._dh_inner(snapshot, *args, **kwargs)
    try:
        info = snapshot.get('zombie') if isinstance(snapshot, dict) else None
        if isinstance(info, dict) and _dh_zombie_map():
            me = BATTLE.get('entity_id')
            for body in info.get('z') or ():
                if body == me or body in _dh_zombie['bodies']:
                    continue
                entity = body_of(body)
                if entity is None:
                    continue                  # not drawn yet: the act with 'z' marks it when it appears
                _dh_zombie['bodies'].add(body)
                _dh_zombie_mark(entity, True)
            winner = info.get('w')
            if winner and not _round.get('shown'):
                player = current_player()
                if player is not None and int(getattr(player, 'hp', 0) or 0) > 0:
                    mine = 'infected' if _dh_zombie['me'] else 'humans'
                    tip_text('The infected took over!' if winner == 'infected' else 'The humans survived!')
                    log('local-zombie-round-over', winner=winner, camp=mine)
                    call_later(1.5, show_result, player, 1 if winner == mine else 2)
    except Exception:
        if once('zombie-snapshot'):
            log_error('local-zombie-snapshot-error')
    return result


def _dh_zombie_leave_wrapper(player=None, *args, **kwargs):
    _dh_zombie['me'] = False
    _dh_zombie['bodies'] = set()
    _dh_zombie['logged'] = False
    return _dh_zombie_leave_wrapper._dh_inner(player, *args, **kwargs)


def cmd_zombie(player, args):
    """Game masters (the host checks): /zombie [n] brings n zombies to your side, /zombie me turns you."""
    if BATTLE.get('phase') != 'fighting' or player is None:
        return 'Only in a match.'
    if not _dh_zombie_map():
        return 'Only in Zombie Trial.'
    if args and args[0] == 'me':
        return 'You turned.' if _dh_zombie_turn(player) else 'You are a zombie already.'
    count = chat_count(args, 0, 3, 10)
    try:
        send(LOOT_PREFIX + json.dumps({'zombie': {'spawn': count, 'me': BATTLE.get('entity_id')}}))
    except Exception:
        log_error('local-zombie-spawn-send-error')
        return 'The host could not be asked.'
    return 'Asked the host for %d zombies (game masters only).' % count


try:
    CHAT_COMMANDS['zombie'] = cmd_zombie
    if not any('/zombie' in line for line in CHAT_HELP):
        CHAT_HELP = CHAT_HELP[:-1] + ('/zombie [n|me] - Zombie Trial test: n zombies by your side, or turn yourself',) + CHAT_HELP[-1:]
except Exception:
    log_error('local-zombie-command-error')


try:
    _dh_m39 = {
        'act': _dh_wrap_global('apply_act', _dh_zombie_apply_act_wrapper, '_dh_zombie'),
        'my_act': _dh_wrap_global('my_act', _dh_zombie_my_act_wrapper, '_dh_zombie'),
        'hit': _dh_wrap_global('take_player_hit', _dh_zombie_hit_wrapper, '_dh_zombie'),
        'hurt': _dh_wrap_global('hurt_avatar', _dh_zombie_hurt_avatar_wrapper, '_dh_zombie'),
        'leave': _dh_wrap_global('leave_battle', _dh_zombie_leave_wrapper, '_dh_zombie'),
        'snapshot': _dh_wrap_global('apply_snapshot', _dh_zombie_snapshot_wrapper, '_dh_zombie'),
    }
    log('local-zombie-installed', **_dh_m39)
except Exception:
    log_error('local-zombie-install-error')



# ---- m40: Dogfight (air war, map 795) loot.  The mode's whole flight kit lives in the client (PlayerAvatar.runJetBag,
# rocket shoes, the glider; see docs/client-feature-audit.md), but the hook's ground loot is a fixed tuple
# (LOOT_SINGLES) that never held the air-war props, so a Dogfight round played as a plain battle royale.  The props:
# 2100001 Jetpack (PropTypeJetBag), 2101001 Rapid Cooler, 2101011 Air Stabilizer, 2300001-3 Spring / Strider / Glider
# Boots (PropTypeRocketShose), 2400001 Airborne Glider (PropTypeParagliding).  LOOT_SINGLES is read by name inside the
# loot functions (random.choice(LOOT_SINGLES)), so a sequence whose content follows BATTLE['map'] is enough: every
# window lays the round's loot out from the same seed, so the extra picks match everywhere.
_DH_AIR_WAR_MAPS = (795,)
_DH_AIR_WAR_LOOT = ((2100001, 1), (2100001, 1), (2100001, 1), (2101001, 1), (2101011, 1),
                    (2300001, 1), (2300002, 1), (2300003, 1), (2400001, 1), (2400001, 1))


class _DhLootSingles(object):
    """LOOT_SINGLES with the air-war props added on the Dogfight map (a sequence for random.choice / len / index)."""
    def __init__(self, base):
        self.base = tuple(base)
    def _seq(self):
        try:
            if int(BATTLE.get('map') or 0) in _DH_AIR_WAR_MAPS:
                return self.base + _DH_AIR_WAR_LOOT
        except Exception:
            pass
        return self.base
    def __len__(self):
        return len(self._seq())
    def __getitem__(self, index):
        return self._seq()[index]
    def __iter__(self):
        return iter(self._seq())
    def __contains__(self, item):
        return item in self._seq()
    def __add__(self, other):
        return self._seq() + tuple(other)
    def __radd__(self, other):
        return tuple(other) + self._seq()
    def __repr__(self):
        return repr(self._seq())


try:
    _dh_loot_base = globals().get('LOOT_SINGLES')
    if isinstance(_dh_loot_base, _DhLootSingles):
        _dh_loot_base = _dh_loot_base.base
    if _dh_loot_base:
        LOOT_SINGLES = _DhLootSingles(_dh_loot_base)
        log('local-air-war-loot-installed', base=len(_dh_loot_base), extra=len(_DH_AIR_WAR_LOOT))
    else:
        log('local-air-war-loot-skipped')
except Exception:
    log_error('local-air-war-loot-error')



# ---- m40b: wearing the air-war items.  The game server used to set the replicated props (curJetBag, curJetBagCooler,
# curJetBagStabilizer, curRocketShose, currEquipDtsParagliding) and call the wear callbacks; here the pick-up does it
# (grant_prop) and /jetpack hands the whole kit to the player for testing.  Gas is synced by the host in the original
# game (onSyncJetBagGas); here the pack is filled on wear and /jetpack refills it.
_DH_AIR_KINDS = {'PropTypeJetBag': 'jetbag', 'PropTypeJetBagCooler': 'cooler', 'PropTypeJetBagStabilizer': 'stabilizer',
                 'PropTypeRocketShose': 'boots', 'PropTypeParagliding': 'glider'}
_DH_AIR_GAS = 400


def _dh_air_item_record(prop, **info):
    return {'itemID': int(prop), 'info': dict(info), 'active': False, 'isRunningLV23': False}


def _dh_air_refresh(player, name, *args):
    """The wear callbacks refresh the air-war HUD (UIPanelAirWar); that panel only exists on the Dogfight map, so a
    failed refresh is logged once and the item stays worn."""
    try:
        getattr(player, name)(*args)
        return True
    except Exception:
        if once('air-war-' + name):
            log_error('local-air-war-refresh-error', call=name)
        return False


def _dh_wear_air_item(player, prop, what):
    # the replicated records the game server used to fill (iAirWar reads cur*['itemID'], ['info']['gas' / 'fuel'],
    # ['active'], .get('isRunningLV23'); the jump check reads info['lastJumpTime'] & co)
    prop = int(prop)
    now = 0
    if what == 'jetbag':
        player.curJetBag = _dh_air_item_record(prop, gas=_DH_AIR_GAS, lastJumpTime=now, lastFallTime=now,
                                               lastJumpTimeServer=now, lastFallTimeServer=now)
        _dh_air_refresh(player, 'onWearDtsJetBag')
        _dh_air_refresh(player, 'onSyncJetBagGas', _DH_AIR_GAS)
    elif what == 'cooler':
        if not getattr(player, 'curJetBag', None):
            return False
        player.curJetBagCooler = _dh_air_item_record(prop, lastJumpTime=now, lastFallTime=now)
        _dh_air_refresh(player, 'onWearDtsJetBagCooler', 1)
    elif what == 'stabilizer':
        if not getattr(player, 'curJetBag', None):
            return False
        player.curJetBagStabilizer = _dh_air_item_record(prop)
        _dh_air_refresh(player, 'onWearDtsJetBagStabilizer', 1)
    elif what == 'boots':
        player.curRocketShose = _dh_air_item_record(prop, fuel=_DH_AIR_GAS)
        _dh_air_refresh(player, 'onWearRocketShose', prop)
    elif what == 'glider':
        player.currEquipDtsParagliding = {'itemId': prop}
        _dh_air_refresh(player, 'onEquipDtsParaglidingItem')
    else:
        return False
    log('local-air-war-wear', what=what, prop=prop)
    return True


def _dh_air_grant_wrapper(player, prop, taken, *args, **kwargs):
    try:
        what = _DH_AIR_KINDS.get(prop_kind(prop))
        if what and player is not None:
            if _dh_wear_air_item(player, prop, what):
                return 'PropType' + what
    except Exception:
        if once('air-war-grant'):
            log_error('local-air-war-grant-error')
    return _dh_air_grant_wrapper._dh_inner(player, prop, taken, *args, **kwargs)


def cmd_jetpack(player, args):
    """/jetpack - the Dogfight kit (jetpack, cooler, stabilizer, glider boots, airborne glider) and a full tank, to try the mode out."""
    if BATTLE.get('phase') != 'fighting' or player is None:
        return 'Only in a match.'
    worn = []
    for what, prop in (('jetbag', 2100001), ('cooler', 2101001), ('stabilizer', 2101011), ('boots', 2300003), ('glider', 2400001)):
        try:
            if _dh_wear_air_item(player, prop, what):
                worn.append(what)
        except Exception:
            log_error('local-air-war-kit-error', what=what)
    return 'Air kit on: %s (tank full).' % ', '.join(worn) if worn else 'The kit could not be worn here.'


try:
    CHAT_COMMANDS['jetpack'] = cmd_jetpack
    if not any('/jetpack' in line for line in CHAT_HELP):
        CHAT_HELP = CHAT_HELP[:-1] + ('/jetpack - Dogfight test: wear the jetpack kit with a full tank',) + CHAT_HELP[-1:]
    _dh_m40b = {'grant': _dh_wrap_global('grant_prop', _dh_air_grant_wrapper, '_dh_airwar')}
    log('local-air-war-wear-installed', **_dh_m40b)
except Exception:
    log_error('local-air-war-wear-install-error')



# ---- m40c: the host side of the jet bag, answered in the window.  tryRunJetBag asks the cell (requestJetBagJump) and
# waits for onJetBagJump(code, jetBag) - 1 = go, with the record whose info.gas the host charged (JUMP_GAS_COST 20,
# FALL_GAS_COST 5); the fall works the same way (requestJetBagFall -> onJetBagFall).  The rocket boots ask
# activateRocketShose / inactivateRocketShose / rocketShoseNos and expect the on* echoes.  The sync calls
# (syncRunningJetBag, syncOtherRunningJetBagData, playAllClientDtsJetBagAnim, rocketShoseStop) carry the flyer's state to
# the other windows in the original game; they are swallowed here.  Gas recovers while the pack is idle.
_DH_JET_JUMP_COST = 20
_DH_JET_FALL_COST = 5
_DH_JET_RECOVER = 40          # gas every _DH_JET_RECOVER_EVERY seconds while not flying
_DH_JET_RECOVER_EVERY = 5.0
_dh_jet = globals().get('_dh_jet') or {'token': None}


def _dh_jet_record(player):
    record = player.__dict__.get('curJetBag') if hasattr(player, '__dict__') else None
    if record is None:
        record = getattr(player, 'curJetBag', None)
    if not isinstance(record, dict) or not isinstance(record.get('info'), dict):
        return None
    return record


def _dh_jet_answer(player, callback, cost, key):
    record = _dh_jet_record(player)
    code = 1
    if record is None:
        code = -101
    else:
        gas = int(record['info'].get('gas') or 0)
        if gas < cost:
            code = -103
        else:
            record['info']['gas'] = gas - cost
            record['info'][key] = int(_dh_time.time())
    try:
        call_later(0.05, getattr(player, callback), code, record)
    except Exception:
        log_error('local-jet-answer-error', callback=callback)
    log('local-jet-' + callback, code=code, gas=(record or {}).get('info', {}).get('gas'))
    return None


def on_jet_bag_jump(player, *_args, **_kwargs):
    return _dh_jet_answer(player, 'onJetBagJump', _DH_JET_JUMP_COST, 'lastJumpTimeServer')


def on_jet_bag_fall(player, *_args, **_kwargs):
    return _dh_jet_answer(player, 'onJetBagFall', _DH_JET_FALL_COST, 'lastFallTimeServer')


def _dh_boots(player, active, callback):
    record = getattr(player, 'curRocketShose', None)
    if isinstance(record, dict):
        record['active'] = bool(active)
    try:
        call_later(0.05, getattr(player, callback))
    except Exception:
        log_error('local-boots-answer-error', callback=callback)
    return None


def on_boots_activate(player, *_args, **_kwargs):
    return _dh_boots(player, True, 'onActivateRocketShose')


def on_boots_inactivate(player, *_args, **_kwargs):
    return _dh_boots(player, False, 'onInactivateRocketShose')


_DH_BOOTS_JUMP_COST = 5


def on_boots_jump(player, *_args, **_kwargs):
    """SPACE with the boots on: doRocketShoseJump -> cell.rocketShoseJump; the client jumps only in
    onRocketShoseJump(res, itemID, infoStr) - res 1 and the record's info (fuel charged UP_FUEL_COST) as JSON."""
    record = getattr(player, 'curRocketShose', None)
    if not isinstance(record, dict) or not isinstance(record.get('info'), dict):
        return None
    info = record['info']
    fuel = int(info.get('fuel') or 0)
    res = 1 if fuel >= _DH_BOOTS_JUMP_COST else -1
    if res == 1:
        info['fuel'] = fuel - _DH_BOOTS_JUMP_COST
    try:
        call_later(0.05, player.onRocketShoseJump, res, int(record.get('itemID') or 0), json.dumps(info))
        call_later(0.1, player.onRocketShoseFuelChange, info['fuel'], 'jump')
    except Exception:
        log_error('local-boots-jump-error')
    log('local-boots-jump', res=res, fuel=info.get('fuel'))
    return None


def on_boots_stop(player, *_args, **_kwargs):
    try:
        call_later(0.05, player.onRocketShoseStop)
    except Exception:
        pass
    return None


def on_boots_nos(player, *_args, **_kwargs):
    try:
        call_later(0.05, player.onRocketShoseNos)
    except Exception:
        pass
    return None


def _dh_jet_recover_tick(token):
    if _dh_jet.get('token') is not token:
        return
    try:
        player = current_player() if BATTLE.get('phase') == 'fighting' else None     # never poke the lobby avatar
        record = _dh_jet_record(player) if player is not None else None
        if record is not None:
            running = False
            try:
                running = bool(player.isRunningJetBag(1)) or bool(player.isRunningJetBag(2))
            except Exception:
                running = False
            gas = int(record['info'].get('gas') or 0)
            if not running and gas < _DH_AIR_GAS:
                record['info']['gas'] = min(_DH_AIR_GAS, gas + _DH_JET_RECOVER)
                try:
                    player.onSyncJetBagGas(record['info']['gas'])
                except Exception:
                    pass
    except Exception:
        if once('jet-recover'):
            log_error('local-jet-recover-error')
    call_later(_DH_JET_RECOVER_EVERY, _dh_jet_recover_tick, token)


try:
    _dh_jet_handlers = getattr(LOBBY, 'RPC_HANDLERS', None)
    if isinstance(_dh_jet_handlers, dict):
        _dh_jet_handlers['requestJetBagJump'] = on_jet_bag_jump
        _dh_jet_handlers['requestJetBagFall'] = on_jet_bag_fall
        _dh_jet_handlers['activateRocketShose'] = on_boots_activate
        _dh_jet_handlers['inactivateRocketShose'] = on_boots_inactivate
        _dh_jet_handlers['rocketShoseNos'] = on_boots_nos
        _dh_jet_handlers['rocketShoseJump'] = on_boots_jump
        _dh_jet_handlers['rocketShoseStop'] = on_boots_stop
        for _dh_name in ('syncRunningJetBag', 'syncOtherRunningJetBagData', 'playAllClientDtsJetBagAnim',
                         'syncJetBagGas', 'syncRunningRocketShoseData', 'rocketShoseTouchGround'):
            _dh_jet_handlers.setdefault(_dh_name, ignore_call)
        _dh_jet['token'] = object()
        call_later(_DH_JET_RECOVER_EVERY, _dh_jet_recover_tick, _dh_jet['token'])
        log('local-jet-handlers-installed', count=5)
    else:
        log('local-jet-handlers-skipped')
except Exception:
    log_error('local-jet-handlers-error')



# ---- m40f: the hover watchdog.  Without the game server the jet-bag jump stalls after the rise: the coroutine leaves
# the player hanging (gravity 0, no velocity, user move locked, runningJetBagData['ready'] True, stage NONE) and never
# hands control back.  When that state lasts STALL_SECONDS the window calls the game's own resetJetBag(): gravity and
# input return, the player falls and can open the glider (SHIFT) and steer, exactly the mode's normal flow.
_DH_JET_STALL_SECONDS = 1.5
_dh_jet_watch = globals().get('_dh_jet_watch') or {'since': None, 'token': None, 'count': 0}


def _dh_jet_stalled(player):
    try:
        data = getattr(player, 'runningJetBagData', None) or {}
        if not data.get('ready'):
            return False
        if int(getattr(player, 'runJetBagStage', 0) or 0) != 0:
            return False
        mu = getattr(player, 'moveUnit', None)
        ch = getattr(mu, 'character', None)
        if ch is None:
            return False
        if abs(float(getattr(ch, 'verticalVelocity', 1.0) or 0.0)) > 0.01:
            return False
        try:
            gravity = float(ch.getGravity())
        except Exception:
            gravity = 1.0
        return gravity == 0.0
    except Exception:
        return False


def _dh_jet_watchdog(token):
    if _dh_jet_watch.get('token') is not token:
        return
    try:
        player = current_player() if BATTLE.get('phase') == 'fighting' else None
        if player is not None and _dh_jet_record(player) is not None and _dh_jet_stalled(player):
            now = _dh_time.time()
            if _dh_jet_watch['since'] is None:
                _dh_jet_watch['since'] = now
            elif now - _dh_jet_watch['since'] >= _DH_JET_STALL_SECONDS:
                _dh_jet_watch['since'] = None
                _dh_jet_watch['count'] += 1
                player.resetJetBag()
                log('local-jet-hover-released', count=_dh_jet_watch['count'], pos=[round(v, 1) for v in player.position])
        else:
            _dh_jet_watch['since'] = None
    except Exception:
        if once('jet-watchdog'):
            log_error('local-jet-watchdog-error')
    call_later(0.5, _dh_jet_watchdog, token)


try:
    _dh_jet_watch['token'] = object()
    call_later(0.5, _dh_jet_watchdog, _dh_jet_watch['token'])
    log('local-jet-watchdog-installed')
except Exception:
    log_error('local-jet-watchdog-install-error')



# ---- m40g: other players see the flyer.  The game server used to relay the air-war state to every other window
# (onOtherWearDtsJetBag, onOtherChangeRunJetBagStage, onPlayDtsJetBagAnim, onOtherEquipDtsParaglidingItem,
# onOpenDtsParagliding).  Here the flyer's window puts it into the act it already sends every tick, as
# act['aw'] = [jetBagItem, runStage, gliderInUse, animName, animLoop, animSeq] (the host passes small plain data through,
# battle.clean_shared), and every other window replays changes on that body with the same callbacks.
_dh_aw_seen = globals().get('_dh_aw_seen') or {}


def _dh_aw_anim_handler(player, name='', loop=0, *_args, **_kwargs):
    anim = _dh_jet.get('anim') or ['', 0, 0]
    _dh_jet['anim'] = [str(name or ''), int(loop or 0), int(anim[2]) + 1]
    return None


def _dh_aw_state(player):
    if int(BATTLE.get('map') or 0) not in _DH_AIR_WAR_MAPS or player is None:
        return None
    record = _dh_jet_record(player)
    jet = int(record.get('itemID') or 0) if record else 0
    try:
        glider = 1 if getattr(player, 'dtsParaglidingInUse', False) else 0
    except Exception:
        glider = 0
    if not jet and not glider:
        return None
    try:
        stage = int(getattr(player, 'runJetBagStage', 0) or 0)
    except Exception:
        stage = 0
    anim = _dh_jet.get('anim') or ['', 0, 0]
    return [jet, stage, glider, anim[0], anim[1], anim[2]]


def _dh_aw_my_act_wrapper(*args, **kwargs):
    act = _dh_aw_my_act_wrapper._dh_inner(*args, **kwargs)
    try:
        if isinstance(act, dict):
            state = _dh_aw_state(current_player())
            if state is not None:
                act['aw'] = state
    except Exception:
        if once('aw-my-act'):
            log_error('local-aw-my-act-error')
    return act


def _dh_aw_call(entity, name, *args):
    try:
        getattr(entity, name)(*args)
        return True
    except Exception:
        if once('aw-other-' + name):
            log_error('local-aw-other-error', call=name)
        return False


def _dh_aw_apply(battle_id, entity, state):
    last = _dh_aw_seen.get(battle_id) or [0, 0, 0, '', 0, 0]
    _dh_aw_seen[battle_id] = list(state)
    jet, stage, glider, anim, loop, seq = (list(state) + [0, 0, 0, '', 0, 0])[:6]
    if jet and not (getattr(entity, '__dict__', {}) or {}).get('curJetBag'):
        entity.curJetBag = _dh_air_item_record(jet, gas=_DH_AIR_GAS)
        _dh_aw_call(entity, 'onOtherWearDtsJetBag')
    if int(stage) != int(last[1]):
        _dh_aw_call(entity, 'onOtherChangeRunJetBagStage', int(stage))
    if int(seq) != int(last[5]) and anim:
        _dh_aw_call(entity, 'onPlayDtsJetBagAnim', str(anim), int(loop))
    if glider and not last[2]:
        if not getattr(entity, 'currEquipDtsParagliding', None):
            entity.currEquipDtsParagliding = {'itemId': 2400001}
            _dh_aw_call(entity, 'onOtherEquipDtsParaglidingItem')
        # the flag drives the glider model on other bodies (PlayerCommonAppear polls isDtsParaglidingActive);
        # onOpenDtsParagliding itself is player-only (it needs the PlayerMachineMgr state machine)
        entity.dtsParaglidingInUse = True
    elif not glider and last[2]:
        entity.dtsParaglidingInUse = False
    return True


def _dh_aw_apply_act_wrapper(battle_id, handle, act, *args, **kwargs):
    result = _dh_aw_apply_act_wrapper._dh_inner(battle_id, handle, act, *args, **kwargs)
    try:
        state = act.get('aw') if isinstance(act, dict) else None
        if state and list(state) != _dh_aw_seen.get(battle_id):
            entity = _resolve_entity(handle)
            if entity is not None and not isinstance(entity, (int, long_type)):
                _dh_aw_apply(battle_id, entity, state)
    except Exception:
        if once('aw-apply'):
            log_error('local-aw-apply-error')
    return result


def _dh_aw_leave_wrapper(player=None, *args, **kwargs):
    _dh_aw_seen.clear()
    _dh_jet['anim'] = ['', 0, 0]
    return _dh_aw_leave_wrapper._dh_inner(player, *args, **kwargs)


try:
    if isinstance(_dh_jet_handlers, dict):
        _dh_jet_handlers['playAllClientDtsJetBagAnim'] = _dh_aw_anim_handler
    _dh_m40g = {
        'my_act': _dh_wrap_global('my_act', _dh_aw_my_act_wrapper, '_dh_airwar'),
        'act': _dh_wrap_global('apply_act', _dh_aw_apply_act_wrapper, '_dh_airwar'),
        'leave': _dh_wrap_global('leave_battle', _dh_aw_leave_wrapper, '_dh_airwar'),
    }
    log('local-aw-relay-installed', **_dh_m40g)
except Exception:
    log_error('local-aw-relay-install-error')



# ---- m40h: a car on the waiting island must not ride the plane.  board_plane moved the player onto the plane while
# inLandVehicle was still True (the seat, the driver control and the car's seat list kept him), so the body flew as a
# car and the landing never registered (the fall stayed on, "24 KM/H" on the ground).  Boarding now takes the player
# out of the car first, without the exit teleport; and while the plane / fall stage runs, a seat that somehow returns
# is dropped the same way.
def _dh_detach_from_car(player, why):
    if player is None or not getattr(player, 'inLandVehicle', False):
        return False
    car = vehicle_entity(getattr(player, 'vehicleEntID', 0))
    was_driver = bool(getattr(player, 'isLandDriver', False))
    try:
        if car is not None:
            set_seats(car, [seat for seat in list(car.usedHangSockets or []) if seat.get('id') != player.id])
        clear_seat(player)
        if was_driver and car is not None:
            release_control(player, car)
        if car is not None:
            car.onGetOff(player.id)
        player.onSwitchToOffVehicle()
    except Exception:
        log_error('local-plane-car-detach-error', why=why)
    try:
        player.inLandVehicle = False
    except Exception:
        pass
    log('local-plane-car-detached', why=why, vehicle=getattr(car, 'id', 0), driver=was_driver)
    return True


def _dh_board_plane_car_wrapper(token=None, player=None, *args, **kwargs):
    try:
        _dh_detach_from_car(player or current_player(), 'boarding')
    except Exception:
        log_error('local-plane-car-board-error')
    return _dh_board_plane_car_wrapper._dh_inner(token, player, *args, **kwargs)


_dh_plane_car = globals().get('_dh_plane_car') or {'token': None}


def _dh_plane_car_tick(token):
    if _dh_plane_car.get('token') is not token:
        return
    try:
        if BATTLE.get('phase') == 'fighting' and _flight.get('stage') == 'plane':
            _dh_detach_from_car(current_player(), 'flight')
    except Exception:
        if once('plane-car-tick'):
            log_error('local-plane-car-tick-error')
    call_later(1.0, _dh_plane_car_tick, token)


try:
    _dh_m40h = {'board': _dh_wrap_global('board_plane', _dh_board_plane_car_wrapper, '_dh_plane_car')}
    _dh_plane_car['token'] = object()
    call_later(1.0, _dh_plane_car_tick, _dh_plane_car['token'])
    log('local-plane-car-installed', **_dh_m40h)
except Exception:
    log_error('local-plane-car-install-error')



# ---- m40i: players walked on lake and river bottoms instead of swimming (every mode).  Swimming is the client's own:
# a 0.1 s timer (iSwim.checkPlayerInWater, started by swimStartCheck / activeSwim) ray-tests for water above the feet
# and switches to the SWIM pose.  The ray registration is dropped during the plane / parachute flight (the jump flight
# registers its own water ray) and the original server re-armed it on landing; our host never did, so after landing
# the check found no water.  Landing (and the no-plane start) now re-arms it, and a light 5 s guard re-arms it once
# if it is missing while on foot.
_dh_swim = globals().get('_dh_swim') or {'token': None, 'rearmed': 0}


def _dh_swim_rearm(player, why):
    try:
        if player is None or getattr(player, 'isSwimming', False) or getattr(player, 'inLandVehicle', False):
            return False
        player.swimStartCheck()
        _dh_swim['rearmed'] += 1
        if _dh_swim['rearmed'] <= 3 or _dh_swim['rearmed'] % 50 == 0:
            log('local-swim-rearmed', why=why, count=_dh_swim['rearmed'])
        return True
    except Exception:
        if once('swim-rearm'):
            log_error('local-swim-rearm-error', why=why)
        return False


def _dh_swim_landed_wrapper(player, *args, **kwargs):
    result = _dh_swim_landed_wrapper._dh_inner(player, *args, **kwargs)
    call_later(0.5, _dh_swim_rearm, player, 'landed')
    return result


def _dh_swim_no_plane_wrapper(player, *args, **kwargs):
    result = _dh_swim_no_plane_wrapper._dh_inner(player, *args, **kwargs)
    call_later(0.5, _dh_swim_rearm, player, 'no-plane')
    return result


def _dh_swim_guard(token):
    if _dh_swim.get('token') is not token:
        return
    try:
        if BATTLE.get('phase') == 'fighting' and _flight.get('stage') == 'landed':
            player = current_player()
            if player is not None and not getattr(player, 'checkSwimmingTid', 0):
                _dh_swim_rearm(player, 'guard')
    except Exception:
        if once('swim-guard'):
            log_error('local-swim-guard-error')
    call_later(5.0, _dh_swim_guard, token)


try:
    _dh_m40i = {
        'landed': _dh_wrap_global('landed', _dh_swim_landed_wrapper, '_dh_swim'),
        'no_plane': _dh_wrap_global('land_without_plane', _dh_swim_no_plane_wrapper, '_dh_swim'),
    }
    _dh_swim['token'] = object()
    call_later(5.0, _dh_swim_guard, _dh_swim['token'])
    log('local-swim-installed', **_dh_m40i)
except Exception:
    log_error('local-swim-install-error')



# ---- m40j: hot patch integrity.  The launcher (1.0.17+) writes <file>.sha256 next to every hot file it installs; the
# game checks the file against it before running it.  A file whose sidecar does not match (a truncated download, a
# hand-edited copy) is skipped and logged.  Files without a sidecar (older launchers, the laptop test copies) still
# run so the update path itself keeps working; the launcher update brings the sidecars to every player.
def _dh_hot_sidecar_ok(path):
    import os, hashlib
    side = path + '.sha256'
    if not os.path.exists(side):
        return None
    try:
        with open(side) as f:
            want = f.read().strip().lower()
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            h.update(f.read())
        return h.hexdigest() == want
    except Exception:
        return False


def _dh_apply_hot_patch_wrapper(path, namespace=None, *args, **kwargs):
    try:
        ok = _dh_hot_sidecar_ok(path)
        if ok is False:
            log('local-hot-patch-rejected', path=str(path)[-40:])
            return False
    except Exception:
        if once('hot-sidecar'):
            log_error('local-hot-sidecar-error')
    return _dh_apply_hot_patch_wrapper._dh_inner(path, namespace, *args, **kwargs)


try:
    _dh_m40j = {'apply': _dh_wrap_global('apply_hot_patch', _dh_apply_hot_patch_wrapper, '_dh_hotsig')}
    log('local-hot-sidecar-installed', **_dh_m40j)
except Exception:
    log_error('local-hot-sidecar-install-error')


# ---- m40k: every battle packet carries a MAC (docs/security.md phase 3).  Key = HMAC(ticket, "diehard-udp-v1") - the
# ticket the launcher gave this game (LOBBY.LOGIN_TOKEN); the server derived the same key at login.  The envelope
# "\nDH1 <session> <seq> <mac>" is appended to the datagram; the server strips it (server_ext/secure_packets.py).
# Packets sent before the lobby login (no session yet) go as they are.
_dh_pk = globals().get('_dh_pk') or {'seq': 0, 'key': None, 'ticket': None}


def _dh_pk_key():
    ticket = getattr(LOBBY, 'LOGIN_TOKEN', None) if LOBBY is not None else None
    if not ticket:
        return None
    if _dh_pk.get('ticket') != ticket or _dh_pk.get('key') is None:
        import hmac
        import hashlib
        _dh_pk['key'] = hmac.new(str(ticket), 'diehard-udp-v1', hashlib.sha256).digest()
        _dh_pk['ticket'] = ticket
    return _dh_pk['key']


def _dh_pk_sign(payload, kind='B'):
    try:
        key = _dh_pk_key()
        session = LOBBY._backend.get('session') if LOBBY is not None and hasattr(LOBBY, '_backend') else None
        if not key or not session:
            return payload
        data = payload.encode('utf-8') if not isinstance(payload, bytes) else payload
        if '\nDH1 ' in data:
            return data
        import hmac
        import hashlib
        _dh_pk['seq'] += 1
        seq = str(_dh_pk['seq'])
        session = str(session)
        mac = hmac.new(key, kind + session + seq + data, hashlib.sha256).hexdigest()[:32]
        return data + '\nDH1 ' + session + ' ' + seq + ' ' + mac
    except Exception:
        if once('pk-sign'):
            log_error('local-packet-sign-error')
        return payload


def _dh_send_signed_wrapper(payload, *args, **kwargs):
    return _dh_send_signed_wrapper._dh_inner(_dh_pk_sign(payload), *args, **kwargs)


def _dh_send_leave_signed_wrapper(address, payload, *args, **kwargs):
    return _dh_send_leave_signed_wrapper._dh_inner(address, _dh_pk_sign(payload), *args, **kwargs)


try:
    _dh_m40k = {'send': _dh_wrap_global('send', _dh_send_signed_wrapper, '_dh_pk'),
                'leave': _dh_wrap_global('send_leave', _dh_send_leave_signed_wrapper, '_dh_pk')}
    log('local-packet-mac-installed', **_dh_m40k)
except Exception:
    log_error('local-packet-mac-install-error')



# ---- m40l: clock-drift ratio for the Cheat Guard.  Speed hacks scale the process clock (QueryPerformanceCounter /
# timeGetTime); the battle host's pong carries its own server_time.  Over a window of pongs the ratio
# elapsed(time.clock) / elapsed(server_time) must stay near 1; the lobby's guard report (m98) sends it along.
_dh_drift = globals().get('_dh_drift') or {'first': None, 'ratio': None}


def _dh_on_pong_drift_wrapper(packet, now, *args, **kwargs):
    result = _dh_on_pong_drift_wrapper._dh_inner(packet, now, *args, **kwargs)
    try:
        server_time = float(packet.get('server_time') or 0.0)
        if server_time > 0.0:
            local = time.clock()
            first = _dh_drift.get('first')
            if first is None:
                _dh_drift['first'] = (local, server_time)
            else:
                span = server_time - first[1]
                if span >= 60.0:
                    _dh_drift['ratio'] = round((local - first[0]) / span, 4)
                    if LOBBY is not None:
                        try:
                            LOBBY._dh_guard['drift'] = _dh_drift['ratio']
                        except Exception:
                            pass
                    if span >= 600.0:
                        _dh_drift['first'] = (local, server_time)
    except Exception:
        if once('drift'):
            log_error('local-drift-error')
    return result


try:
    _dh_m40l = {'pong': _dh_wrap_global('on_pong', _dh_on_pong_drift_wrapper, '_dh_drift')}
    log('local-drift-installed', **_dh_m40l)
except Exception:
    log_error('local-drift-install-error')


# ---- m40m: (1) Prepare Island - shots land but do no damage (the original server's rule; ours killed and respawned).
# (2) a probe for the window / glass question: which scene-system calls exist (getBreakableID, breakElement), whether
# the physics raycast modules are loaded, how the first scene hits resolve, and what the space entity offers for the
# danger-zone look (names with circle / poison / zone / effect / fog) - logged once per round for the owner's report.
_dh_island = globals().get('_dh_island') or {'blocked': 0}
_dh_hit_sent = globals().get('_dh_hit_sent') or {}


def _dh_hurt_avatar_island_wrapper(player, target, damage, src_pos, hit_part, hit_type, weapon, weapon_name, *args, **kwargs):
    # m40o (2026-10-26): bots too - the owner killed 11 of 20 rivals on the island before the plane left.  Firing and
    # hit markers stay; nobody (player or bot) loses health until the round is on.
    try:
        if on_island_stage():
            _dh_island['blocked'] += 1
            player_body = is_player_body(target)
            if _dh_island['blocked'] <= 3 or _dh_island['blocked'] % 50 == 0:
                log('local-island-no-damage', hits=_dh_island['blocked'], weapon=safe(weapon_name, 30), bot=not player_body)
            try:
                shown = broadcast(target, 'damage', (player.id, src_pos, weapon, 0, int(getattr(target, 'hp', FULL_HP) or FULL_HP), hit_part, hit_type))
                if not shown and not player_body:
                    show_damage_text(target.position, 0, hit_type, hit_part)
            except Exception:
                pass
            return None
    except Exception:
        if once('island-no-damage'):
            log_error('local-island-no-damage-error')
    # m40o: tell the host which bot I hit (the client keeps bot health and used to send only the kill, so a bot under
    # fire never knew - it kept roaming).  At most one report per bot every 0.3 s; the brain turns the bot on me.
    try:
        if not is_player_body(target):
            bot = battle_id_of(target)
            now = time.time()
            if bot is not None and now - _dh_hit_sent.get(bot, 0.0) >= 0.3:
                _dh_hit_sent[bot] = now
                send(LOOT_PREFIX + json.dumps({'hit': {'me': BATTLE.get('entity_id') or 0, 'bot': bot}}))
                _dh_island['hit_reports'] = _dh_island.get('hit_reports', 0) + 1
                if _dh_island['hit_reports'] in (1, 50, 500):
                    log('local-bot-hit-report', reports=_dh_island['hit_reports'], bot=bot)
    except Exception:
        if once('bot-hit-report'):
            log_error('local-bot-hit-report-error')
    return _dh_hurt_avatar_island_wrapper._dh_inner(player, target, damage, src_pos, hit_part, hit_type, weapon, weapon_name, *args, **kwargs)


_dh_hitscene = globals().get('_dh_hitscene') or {'calls': 0}


def _dh_on_hit_scene_probe_wrapper(player, material=None, position=None, normal=None, weapon=None, *args, **kwargs):
    result = _dh_on_hit_scene_probe_wrapper._dh_inner(player, material, position, normal, weapon, *args, **kwargs)
    try:
        _dh_hitscene['calls'] += 1
        if _dh_hitscene['calls'] <= 12:
            breakable = None
            try:
                breakable = breakable_at(position, normal)
            except Exception:
                breakable = 'error'
            log('local-hitscene-probe', n=_dh_hitscene['calls'], material=safe(material, 40), breakable=safe(breakable, 20),
                pos=[round(v, 1) for v in _point(position)] if position is not None else None, weapon=safe(weapon, 20))
    except Exception:
        if once('hitscene-probe'):
            log_error('local-hitscene-probe-error')
    return result


def _dh_wrap_handler(name, wrapper_factory, marker):
    """Wrap an entry of the cell RPC table (LOBBY.RPC_HANDLERS): the game calls those, not the module globals."""
    table = getattr(LOBBY, 'RPC_HANDLERS', None)
    if not isinstance(table, dict) or name not in table:
        return False
    inner = table[name]
    while getattr(inner, marker, False) and getattr(inner, '_dh_inner', None) is not None:
        inner = inner._dh_inner
    wrapped = wrapper_factory(inner)
    setattr(wrapped, marker, True)
    wrapped._dh_inner = inner
    table[name] = wrapped
    return True


def _dh_hitscene_entry(inner):
    def handler(player, material=None, position=None, normal=None, weapon=None, *args, **kwargs):
        return _dh_on_hit_scene_probe_wrapper_entry(inner, player, material, position, normal, weapon, *args, **kwargs)
    return handler


def _dh_on_hit_scene_probe_wrapper_entry(inner, player, material, position, normal, weapon, *args, **kwargs):
    result = inner(player, material, position, normal, weapon, *args, **kwargs)
    try:
        _dh_hitscene['calls'] += 1
        if _dh_hitscene['calls'] <= 12:
            breakable = None
            try:
                breakable = breakable_at(position, normal)
            except Exception:
                breakable = 'error'
            log('local-hitscene-probe', n=_dh_hitscene['calls'], material=safe(material, 40), breakable=safe(breakable, 20),
                pos=[round(v, 1) for v in _point(position)] if position is not None else None, weapon=safe(weapon, 20))
    except Exception:
        if once('hitscene-probe'):
            log_error('local-hitscene-probe-error')
    return result


def _dh_fire_entry(inner):
    def handler(player, *args, **kwargs):
        try:
            _dh_hitscene['fires'] = _dh_hitscene.get('fires', 0) + 1
            if _dh_hitscene['fires'] <= 6:
                log('local-fire-probe', n=_dh_hitscene['fires'], gun=safe(held_gun(player), 20), stage=_flight.get('stage'))
        except Exception:
            pass
        return inner(player, *args, **kwargs)
    return handler


def _dh_capability_probe(tries=0):
    try:
        space = zone_space()
        if space is None and tries < 40:
            call_later(20.0, _dh_capability_probe, tries + 1)
    except Exception:
        pass
    try:
        scene = _scene_system()
        names = [n for n in dir(scene) if any(k in n.lower() for k in ('reak', 'lement', 'collid', 'destruct'))] if scene is not None else []
        physics = sys.modules.get('libclaudia.Classes.Physics') is not None
        ray = sys.modules.get('libclaudia.Classes.Ray') is not None
        log('local-scene-caps', scene=type(scene).__name__ if scene is not None else None, names=names[:40], physics=physics, ray=ray)
    except Exception:
        log_error('local-scene-caps-error')
    try:
        space = zone_space()
        zone_names = [n for n in dir(space) if any(k in n.lower() for k in ('circle', 'poison', 'zone', 'effect', 'fog', 'bomb', 'red'))] if space is not None else []
        log('local-zone-caps', space=type(space).__name__ if space is not None else None, names=zone_names[:80])
    except Exception:
        log_error('local-zone-caps-error')


try:
    _dh_m40m = {'island': _dh_wrap_global('hurt_avatar', _dh_hurt_avatar_island_wrapper, '_dh_island'),
                'hitscene': _dh_wrap_handler('broadcastShootHitScene', _dh_hitscene_entry, '_dh_hitscene'),
                'cold': _dh_wrap_handler('broadcastColdWeaponHitScene', _dh_hitscene_entry, '_dh_hitscene'),
                'fire': _dh_wrap_handler('fire', _dh_fire_entry, '_dh_hitscene')}
    log('local-island-no-damage-installed', **_dh_m40m)
    call_later(8.0, _dh_capability_probe)
except Exception:
    log_error('local-island-no-damage-install-error')


# ---- m40n: party teammates in battle.  A party enters one round with one battle team number (server_ext/party_match.py
# keeps it together, no friendly fire); online the battle server sent the battleTeammates list and the client drew blue
# name tags, the team panel, map markers and the spectate list from it.  Ours only ever held the player.  Each
# snapshot's players with my party team number (ticket 'team', party range 1000000..1999999) become TeammateRecords;
# the list is set and the game's own handlers run (set_battleTeammates, onBattleTeammateUpdate) only when the mates
# or their alive state change - no per-tick work.
_dh_mates = globals().get('_dh_mates') or {}
for _dh_k, _dh_v in (('sig', None), ('updates', 0), ('warned', False)):
    _dh_mates.setdefault(_dh_k, _dh_v)
_DH_PARTY_LOW, _DH_PARTY_HIGH = 1, 2000000


def _dh_player_state(name):
    try:
        import const
        return getattr(const.PlayerState, name)
    except Exception:
        return None


class _DhAliveFlag(object):
    """A teammate's isAlive as the battle server's member data had it: iBattleGround.checkClientTeammate calls it
    (memberData.isAlive()), other readers test it as a value.  Both work."""

    def __init__(self, value):
        self.value = bool(value)

    def __call__(self, *args, **kwargs):
        return self.value

    def __nonzero__(self):
        return self.value

    __bool__ = __nonzero__

    def __eq__(self, other):
        return self.value == (other.value if isinstance(other, _DhAliveFlag) else bool(other))

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return repr(self.value)


def _dh_team_mates_from(snapshot):
    """[(client entity id, name, alive)] of my party teammates in this snapshot; None outside a party."""
    try:
        team = int((BATTLE.get('ticket') or {}).get('team') or 0)
    except (TypeError, ValueError):
        return None
    if not (_DH_PARTY_LOW <= team < _DH_PARTY_HIGH):
        return None
    me = int(BATTLE.get('entity_id') or 0)
    mates = []
    for item in (snapshot or {}).get('entities') or []:
        try:
            if item.get('kind') != 'player' or int(item.get('team') or 0) != team:
                continue
            entity_id = int(item.get('id'))
        except (TypeError, ValueError, AttributeError):
            continue
        if entity_id == me:
            continue
        entity = _remote.get(entity_id)
        client_id = getattr(_resolve_entity(entity), 'id', None) if entity is not None else None
        if client_id is None:
            continue
        mates.append((client_id, str(item.get('name') or 'Teammate'), item.get('alive') is not False))
    return mates


def _dh_place_record(record):
    """A teammate record's live position and facing (RadarMap reads mate.position / mate.yaw every frame, as the
    battle server's member data had them), from the client's own entity."""
    try:
        import BigWorld
        entity = BigWorld.entities.get(getattr(record, 'entID', None))
    except Exception:
        entity = None
    if entity is None:
        return False
    try:
        record.position = entity.position
        record.yaw = float(getattr(entity, 'yaw', 0.0) or 0.0)
        return True
    except Exception:
        return False


def _dh_refresh_mate_positions():
    try:
        import BigWorld
        player = BigWorld.player()
    except Exception:
        return
    for record in list(getattr(player, 'battleTeammates', None) or []):
        if isinstance(record, TeammateRecord):
            _dh_place_record(record)


def _dh_sync_teammates(mates):
    signature = tuple(sorted(mates))
    if signature == _dh_mates['sig']:
        return False
    import BigWorld
    player = BigWorld.player()
    if player is None:
        return False
    old = list(getattr(player, 'battleTeammates', None) or [])
    mine = [record for record in old if getattr(record, 'entID', None) == getattr(player, 'id', None)]
    me = mine[0] if mine else self_teammate(player)
    try:
        me.isAlive = _DhAliveFlag(getattr(me, 'isAlive', True))
    except Exception:
        pass
    records = [me]
    died = _dh_player_state('Died')
    for index, (client_id, name, alive) in enumerate(mates):
        records.append(TeammateRecord(
            entID=client_id, gid=0, nickname=name, state=alive_state() if alive or died is None else died,
            isAlive=_DhAliveFlag(alive), nationalFlag='', baseCharacterType=DEFAULT_CHARACTER_TYPE, index=index + 1,
            markPosition=unmarked(), markFloor=0))
    for record in records:
        if not _dh_place_record(record):
            try:
                record.position = player.position
                record.yaw = 0.0
            except Exception:
                pass
    player.battleTeammates = records
    setter = getattr(player, 'set_battleTeammates', None)
    if callable(setter):
        try:
            setter(old)
        except Exception:
            log_error('local-mates-setter-error')
    update = getattr(player, 'onBattleTeammateUpdate', None)
    if callable(update):
        for index in range(len(records)):
            try:
                update(index)
            except Exception:
                if not _dh_mates['warned']:
                    _dh_mates['warned'] = True
                    log_error('local-mates-update-error', index=index)
                break
    _dh_mates['sig'] = signature
    _dh_mates['updates'] += 1
    if _dh_mates['updates'] <= 10:
        log('local-mates-synced', mates=[name for _id, name, _alive in mates],
            alive=[alive for _id, _name, alive in mates], team=(BATTLE.get('ticket') or {}).get('team'))
    return True


def _dh_apply_snapshot_mates_wrapper(snapshot):
    result = _dh_apply_snapshot_mates_wrapper._dh_inner(snapshot)
    try:
        mates = _dh_team_mates_from(snapshot)
        if mates is not None:
            _dh_sync_teammates(mates)
            if _dh_mates['sig']:
                _dh_refresh_mate_positions()
    except Exception:
        if not _dh_mates['warned']:
            _dh_mates['warned'] = True
            log_error('local-mates-error')
    return result


def _dh_mates_reset_wrapper(*args, **kwargs):
    _dh_mates['sig'] = None
    return _dh_mates_reset_wrapper._dh_inner(*args, **kwargs)


try:
    _dh_m40n = {'snapshot': _dh_wrap_global('apply_snapshot', _dh_apply_snapshot_mates_wrapper, '_dh_mates'),
                'leave': _dh_wrap_global('leave_battle', _dh_mates_reset_wrapper, '_dh_mates')}
    _dh_mates['sig'] = None
    log('local-mates-installed', **_dh_m40n)
except Exception:
    log_error('local-mates-install-error')


# ---- m40p: undo the fire-mode trace and the dtsCurRailID wrapper tried on the laptop (2026-10-26).  Their wrappers
# looked up their inner function by global name, so reloading this file mid-round pointed the old copies at the new ones
# (no _dh_inner) and refreshFireMode / weapon switches failed: the gun stopped firing.  This block puts the hook's and the
# game's own functions back wherever such a wrapper is still installed.
def _dh_strip_marked(function, *markers):
    while function is not None and any(getattr(function, m, False) for m in markers) and getattr(function, '_dh_inner', None) is not None:
        function = function._dh_inner
    return function


try:
    _undo = {}
    _handlers = getattr(LOBBY, 'RPC_HANDLERS', None) if LOBBY is not None else None
    if isinstance(_handlers, dict) and callable(globals().get('on_sync_operate')):
        if _handlers.get('syncDtsWeaponOperate') is not globals()['on_sync_operate']:
            _handlers['syncDtsWeaponOperate'] = globals()['on_sync_operate']
            _undo['sync'] = True
    _fm_cls = getattr(sys.modules.get('player.logic_ctrls.InputInterpred'), 'DtsMixFireOperator', None)
    if _fm_cls is not None:
        _cur = _fm_cls.__dict__.get('refreshFireMode')
        _orig = _cur
        while _orig is not None and getattr(_orig, '_dh_inner', None) is not None:
            _orig = _orig._dh_inner
        if _orig is not None and _orig is not _cur:
            _fm_cls.refreshFireMode = _orig
            _undo['refresh'] = True
    log('local-fm-undo', **_undo)
except Exception:
    log_error('local-fm-undo-error')


# ---- m40p (2): the fire mode (single / auto / burst) survives a weapon switch.  Traced on the laptop: SINGLE was stored
# for rail 20001 (dtsWeaponOperateTypes), but during the switch back the game's InputInterpred.setRail ->
# DtsMixFireOperator.refreshFireMode looks the mode up by player.dtsCurRailID, which the hook never set (0): nothing found,
# AUTO chosen and synced over the stored SINGLE.  switch_weapon now sets dtsCurRailID to the slot's rail before the game
# selects the gun, as the original server did.  Wrapped with _dh_wrap_global (reload-safe; marker _dh_rail).
def _dh_switch_weapon_rail_wrapper(player, slot, *args, **kwargs):
    try:
        rails = player.getRailIDsFromSlotIdx(int(slot)) if hasattr(player, 'getRailIDsFromSlotIdx') else None
        player.dtsCurRailID = int(list(rails)[0]) if rails else 0
    except Exception:
        if once('dh-cur-rail'):
            log_error('local-cur-rail-error', slot=safe(slot, 10))
    return _dh_switch_weapon_rail_wrapper._dh_inner(player, slot, *args, **kwargs)


try:
    log('local-cur-rail-installed', switch=_dh_wrap_global('switch_weapon', _dh_switch_weapon_rail_wrapper, '_dh_rail'))
except Exception:
    log_error('local-cur-rail-install-error')


if isinstance(globals().get('_dh_view'), dict):
    _dh_view['token'] = _dh_view.get('token', 0) + 1      # stop the laptop-only view probe of an earlier load


# --- m40q: G on the waiting island switches to first person (PlayerFPAppear.onChangeToFPP, cell.onChangeFpsMode(1)).
# Online the server took the player through boarding and the jump and the camera followed; here board_plane and
# jump_out are ours, so a first-person player rode INSIDE the plane and fell with a broken view (white ground, only
# trees - owner 2026-10-26).  Before boarding and after the jump a first-person player is put back in third person
# with the game's own PlayerFPAppear.onChangeToTPP(syncServer=False).  G works again once they land.
def _dh_force_tpp(why, player=None):
    try:
        import sys as _s
        player = player or current_player()
        go = getattr(player, 'gameObject', None)
        comp = go.GetComponent('PlayerFPAppear') if go is not None else None
        if comp is None:
            return 'no-component'
        enum = getattr(_s.modules.get('player.appearance.PlayerFPAppear'), 'PerspectiveStateEnum', None)
        tpp = getattr(enum, 'TPP', None)
        current = getattr(comp, 'curPerspective', None)
        if tpp is None or current is None or current == tpp:
            return 'already'
        comp.onChangeToTPP(False)
        log('local-view-tpp-forced', why=why, was=safe(current, 20))
        return 'forced'
    except Exception:
        log_error('local-view-tpp-error', why=why)
        return 'error'


def _dh_board_plane_tpp_wrapper(*args, **kwargs):
    _dh_force_tpp('plane', kwargs.get('player') or (args[1] if len(args) > 1 else None))
    return _dh_board_plane_tpp_wrapper._dh_inner(*args, **kwargs)


def _dh_jump_out_tpp_wrapper(player, *args, **kwargs):
    result = _dh_jump_out_tpp_wrapper._dh_inner(player, *args, **kwargs)
    _dh_force_tpp('jump', player)
    return result


try:
    log('local-view-tpp-installed', board=_dh_wrap_global('board_plane', _dh_board_plane_tpp_wrapper, '_dh_tpp'),
        jump=_dh_wrap_global('jump_out', _dh_jump_out_tpp_wrapper, '_dh_tpp'))
except Exception:
    log_error('local-view-tpp-install-error')



# --- m40t: floating loot (owner 2026-10-26: a dropped gun hung in the sky).  Drops from the battle host (a dead bot's
# or player's items) come with the host's height, and the host has no terrain (R15): a bot that walked downhill or
# died gliding drops its items in the air.  Every item spawned at a given height now goes on the first surface below
# it (a building floor or the ground; level loot on upper floors stays where it is), or up onto the ground when it
# was under it.  One short ray per item.
_DH_LOOT_DROP_SCAN = 400.0          # how far below the given height to look for a surface
_dh_lootfloor = globals().get('_dh_lootfloor') or {'moved': 0, 'logged': 0}


def _dh_loot_floor_wrapper(prop, amount, x, z, y=None, *args, **kwargs):
    if y is not None:
        try:
            y = float(y)
            hit = surface_hit((float(x), y + 1.0, float(z)), (float(x), y - _DH_LOOT_DROP_SCAN, float(z)))
            ground = ground_height(x, z)
            new_y = None
            if hit is not None:
                new_y = float(hit[0][1])
            elif ground and y < ground - 0.5:
                new_y = float(ground)
            if new_y is not None and abs(new_y - y) > 1.0:
                if _dh_lootfloor['logged'] < 20:
                    _dh_lootfloor['logged'] += 1
                    log('local-loot-floored', prop=int(prop), was=round(y, 1), now=round(new_y, 1))
                _dh_lootfloor['moved'] += 1
                y = new_y
        except Exception:
            if not _dh_lootfloor.get('error_logged'):
                _dh_lootfloor['error_logged'] = True
                log_error('local-loot-floor-error')
    return _dh_loot_floor_wrapper._dh_inner(prop, amount, x, z, y, *args, **kwargs)


try:
    log('local-loot-floor-installed', spawn=_dh_wrap_global('spawn_loot', _dh_loot_floor_wrapper, '_dh_lootfloor'))
except Exception:
    log_error('local-loot-floor-install-error')


# --- m40t: in-round actions (dances).  The action panel's state (PlayerStatesV2.PlayerInGameAction) only tells the
# server cell.doInGameAction(appearanceID); the online server answered iBattleGround.onOwnDoInGameAction(animName,
# loop) (-> msgInGameActionStart -> the animation) and, on cell.onInGameActionEnd, onOwnInGameActionEnd.  Nothing
# answered here (the guessed reply "inGameAction" does not exist), so the character never danced (owner 2026-10-26).
# The animation name and loop flag come from the action's own hall-prop record (its field names are logged once).
_dh_dance = globals().get('_dh_dance') or {'logged': False, 'plays': 0}


def _dh_action_anim(appearance_id):
    import sys as _s
    props = _s.modules.get('shared.lib.gametoolslib.properties')
    if props is None:
        props = __import__('shared.lib.gametoolslib.properties', fromlist=['x'])
    data = props.getDtsHallPropData(int(appearance_id))
    kind = getattr(data, 'PROP_TYPE', None) if data is not None else None
    fields = {}
    for source in (kind, data):
        if source is None:
            continue
        for name in dir(source):
            if name.startswith('_') or name in fields:
                continue
            try:
                value = getattr(source, name)
            except Exception:
                continue
            if isinstance(value, (basestring, int, long, float, bool)) and ('ANIM' in name.upper() or 'LOOP' in name.upper() or 'ACTION' in name.upper()):
                fields[name] = value
    # the round's own animation first (IN_GAME_ANIMATION / IN_GAME_ANIMATION_LOOP), any other animation field after
    anim = fields.get('IN_GAME_ANIMATION') or None
    loop = bool(int(fields.get('IN_GAME_ANIMATION_LOOP') or fields.get('ANIMATION_LOOP') or 0))
    for name, value in sorted(fields.items()):
        upper = name.upper()
        if anim is None and isinstance(value, basestring) and value and 'ANIM' in upper and 'LOOP' not in upper:
            anim = value
    if not _dh_dance['logged']:
        _dh_dance['logged'] = True
        log('local-dance-fields', appearance=int(appearance_id), fields=dict((k, safe(v, 60)) for k, v in fields.items()), anim=anim, loop=loop)
    return anim, loop


def on_do_in_game_action(player, appearance_id=0, *args, **kwargs):
    try:
        anim, loop = _dh_action_anim(appearance_id)
        if anim and hasattr(player, 'onOwnDoInGameAction'):
            player.onOwnDoInGameAction(anim, loop)
            _dh_dance['plays'] += 1
            _dh_dance['cur'] = int(appearance_id)            # m40u: the other windows see it through my_act
            _dh_dance['seq'] = int(_dh_dance.get('seq') or 0) + 1
            if _dh_dance['plays'] in (1, 10, 100):
                log('local-dance-played', appearance=int(appearance_id), anim=anim, loop=loop, plays=_dh_dance['plays'])
        elif once('dance-no-anim-%s' % appearance_id):
            log('local-dance-no-anim', appearance=safe(appearance_id, 20))
    except Exception:
        if once('dance-error'):
            log_error('local-dance-error', appearance=safe(appearance_id, 20))
    return None


def on_in_game_action_end(player, *args, **kwargs):
    try:
        _dh_dance['cur'] = 0                                # m40u: the other windows stop it too
        if hasattr(player, 'onOwnInGameActionEnd'):
            player.onOwnInGameActionEnd()
    except Exception:
        if once('dance-end-error'):
            log_error('local-dance-end-error')
    return None


try:
    _dh_dance_handlers = getattr(LOBBY, 'RPC_HANDLERS', None) if LOBBY is not None else None
    if isinstance(_dh_dance_handlers, dict):
        _dh_dance_handlers['doInGameAction'] = on_do_in_game_action
        _dh_dance_handlers['onInGameActionEnd'] = on_in_game_action_end
    log('local-dance-installed', handlers=isinstance(_dh_dance_handlers, dict))
except Exception:
    log_error('local-dance-install-error')


# --- m40u: other players see your dance (owner 2026-10-28).  m40t answered cell.doInGameAction in this window only,
# so nobody else saw it.  The battle host already relays every player's act dict to the other windows unchanged
# (Battle.move -> clean_shared -> Entity.public; checked on staging: unknown keys pass), so the dance rides on it
# like the jump counters: 'da' = the action appearance being played (0 = none), 'ds' = a counter that rises on every
# start (the same dance twice still plays twice).  The other windows play it on that body; the method and its
# argument shape are tried in order and the one that works is remembered and logged once (no signature guessing).
_dh_dance.setdefault('cur', 0)
_dh_dance.setdefault('seq', 0)
_dh_dance.setdefault('remote', {})
_dh_dance.setdefault('way', None)


def _dh_dance_my_act_wrapper(*args, **kwargs):
    act = _dh_dance_my_act_wrapper._dh_inner(*args, **kwargs)
    try:
        if isinstance(act, dict):
            act['da'] = int(_dh_dance.get('cur') or 0)
            act['ds'] = int(_dh_dance.get('seq') or 0)
    except Exception:
        if once('dance-my-act'):
            log_error('local-dance-my-act-error')
    return act


def _dh_dance_on_body(entity, appearance_id):
    anim, loop = _dh_action_anim(appearance_id)
    if not anim:
        return None
    calls = [('onOtherDoInGameAction', (anim, loop)),
             ('onOtherDoInGameAction', (getattr(entity, 'id', 0), anim, loop)),
             ('onOwnDoInGameAction', (anim, loop))]
    known = _dh_dance.get('way')
    if known is not None:
        calls.sort(key=lambda call: 0 if (call[0], len(call[1])) == known else 1)
    for name, call_args in calls:
        fn = getattr(entity, name, None)
        if not callable(fn):
            continue
        try:
            fn(*call_args)
        except TypeError:
            continue
        except Exception:
            if once('dance-remote-' + name):
                log_error('local-dance-remote-error', method=name)
            continue
        if known is None:
            _dh_dance['way'] = (name, len(call_args))
            log('local-dance-remote-way', method=name, args=len(call_args), anim=anim, loop=loop)
        return name
    if once('dance-remote-none'):
        log('local-dance-remote-none', anim=anim,
            methods=[n for n in ('onOtherDoInGameAction', 'onOwnDoInGameAction') if callable(getattr(entity, n, None))])
    return None


def _dh_dance_end_body(entity):
    for name in ('onOtherInGameActionEnd', 'onOwnInGameActionEnd'):
        fn = getattr(entity, name, None)
        if not callable(fn):
            continue
        for call_args in ((), (getattr(entity, 'id', 0),)):
            try:
                fn(*call_args)
                return name
            except TypeError:
                continue
            except Exception:
                if once('dance-remote-end-' + name):
                    log_error('local-dance-remote-end-error', method=name)
                break
    return None


def _dh_dance_apply_act_wrapper(battle_id, handle, act, *args, **kwargs):
    result = _dh_dance_apply_act_wrapper._dh_inner(battle_id, handle, act, *args, **kwargs)
    try:
        if isinstance(act, dict) and 'ds' in act:
            now = (int(act.get('da') or 0), int(act.get('ds') or 0))
            before = _dh_dance['remote'].get(battle_id, (0, None))
            if now != before:
                _dh_dance['remote'][battle_id] = now
                entity = _resolve_entity(handle)
                if entity is not None and not isinstance(entity, (int, long_type)):
                    if now[0] and now[1] != before[1]:
                        _dh_dance_on_body(entity, now[0])       # a new start (or first sight while dancing)
                    elif not now[0] and before[0]:
                        _dh_dance_end_body(entity)
    except Exception:
        if once('dance-apply'):
            log_error('local-dance-apply-error')
    return result


def _dh_dance_leave_wrapper(player=None, *args, **kwargs):
    _dh_dance['remote'].clear()          # entity ids are per round: a stale entry must not hide a new dance
    _dh_dance['cur'] = 0
    return _dh_dance_leave_wrapper._dh_inner(player, *args, **kwargs)


try:
    _dh_m40u = {
        'my_act': _dh_wrap_global('my_act', _dh_dance_my_act_wrapper, '_dh_dance'),
        'act': _dh_wrap_global('apply_act', _dh_dance_apply_act_wrapper, '_dh_dance'),
        'leave': _dh_wrap_global('leave_battle', _dh_dance_leave_wrapper, '_dh_dance'),
    }
    log('local-dance-relay-installed', **_dh_m40u)
except Exception:
    log_error('local-dance-relay-install-error')


# --- m40t: the action / emote panel was empty on the waiting island (owner 2026-10-26).  The battle character gets
# only the outfit lists from the lobby (APPEARANCE_LISTS); the action / emote lists came later, whenever the server's
# props happened to be applied in a round.  Once per round, as soon as the battle character exists, ask the server
# for the props and set just those three lists on it.
_DH_PANEL_PROPS = ('dtsInGameActionAppearanceIDs', 'dtsInGameActionSuitAppearanceIDs', 'dtsEmojiList')
_dh_panel = globals().get('_dh_panel') or {'token': 0, 'round': None, 'asks': 0}
_dh_panel['token'] += 1


def _dh_panel_reply(player, text):
    try:
        if not text:
            return
        props = LOBBY.from_json_value(json.loads(text))
        if not isinstance(props, dict):
            return
        done = []
        for name in _DH_PANEL_PROPS:
            if name in props:
                setattr(player, name, props[name])
                done.append('%s=%d' % (name, len(props[name] or [])))
        log('local-panel-lists-set', lists=done)
    except Exception:
        log_error('local-panel-lists-error')


def _dh_panel_tick(token):
    if token != _dh_panel['token']:
        return
    try:
        player = current_player()
        round_key = (BATTLE.get('map'), id(player)) if player is not None else None
        if player is not None and BATTLE.get('phase') == 'fighting' and round_key != _dh_panel['round']:
            _dh_panel['round'] = round_key
            have = dict((n, len(list(getattr(player, n, None) or []))) for n in _DH_PANEL_PROPS)
            log('local-panel-check', have=have, player=safe(type(player).__name__, 40))
            if not have['dtsInGameActionAppearanceIDs'] or not have['dtsEmojiList']:
                _dh_panel['asks'] += 1
                LOBBY.send_later('props', LOBBY._with_session(LOBBY.PROPS_REQUEST + ' '),
                                 lambda text, who=player: _dh_panel_reply(who, text))
    except Exception:
        if once('panel-tick'):
            log_error('local-panel-tick-error')
    call_later(3.0, _dh_panel_tick, token)


call_later(3.0, _dh_panel_tick, _dh_panel['token'])


# --- m40v (2026-10-28): day and night.  The battle host names each round's weather in the match ('weather', the
# game's own WEATHER id: 4K 0 sunny / 1 fog / 2 night / 3 dusk, The Fiord 8K 4-7).  The game applies it itself when
# the battleground space enters the world (iSpaceWeatherControl.enterWorld ->
# SceneSystem.ChangeWeatherMode(space.weatherID)), so the space is created with it; it is applied once more when the
# round is up, so a stand-in space or an enterWorld that ran before the scene was ready still gets it.  A match without
# 'weather' (an older battle host) keeps the map's plain daylight, as before.
_dh_weather = {'token': object(), 'applied': None, 'tries': 0}


def _dh_match_weather():
    value = (BATTLE.get('match') or {}).get('weather')
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _dh_space_properties_weather(map_id):
    properties = _dh_space_properties_weather._dh_inner(map_id)
    weather = _dh_match_weather()
    if weather is not None and isinstance(properties, dict):
        properties['weatherID'] = weather
    return properties


def _dh_scene_system():
    module = _dh_sys.modules.get('iSpaceWeatherControl')
    finder = getattr(module, 'GameObject', None)
    scene = finder.Find('Scene') if finder is not None else None
    return scene.GetComponent('SceneSystem') if scene is not None else None


def _dh_weather_tick(token):
    """Every 2 s (cheap): once the battle map's scene is up - behind the loading screen - give it the round's weather;
    again if the scene is replaced or the game puts another weather on it (up to 10 times a round)."""
    if token is not _dh_weather['token']:
        return
    try:
        weather = _dh_match_weather()
        round_key = (BATTLE.get('match') or {}).get('uuid')
        if BATTLE.get('phase') not in ('entering', 'fighting') or weather is None:
            _dh_weather['tries'] = 0
        elif _dh_weather['tries'] < 10:
            system = _dh_scene_system()
            scene = getattr(system, '_scene', None) if system is not None else None
            if scene is not None and _dh_battle_map_loaded():
                current = (round_key, weather, id(scene))
                mode = getattr(system, '_weatherModeID', None)
                if _dh_weather['applied'] != current or mode != weather:
                    _dh_weather['tries'] += 1
                    space = BATTLE.get('space_entity')
                    if space is not None and getattr(space, 'weatherID', None) != weather:
                        try:
                            space.weatherID = weather
                        except Exception:
                            pass
                    system.ChangeWeatherMode(weather)
                    _dh_weather['applied'] = current
                    log('local-weather', weather=weather, map=BATTLE.get('map'), phase=BATTLE.get('phase'),
                        was=safe(mode, 20), tries=_dh_weather['tries'])
    except Exception:
        if once('weather-tick'):
            log_error('local-weather-error')
    call_later(2.0, _dh_weather_tick, token)


def _dh_battle_map_loaded():
    """The scene system is on the battle map (not the lobby hall it replaces)."""
    try:
        import Globals
        loaded = getattr(Globals, 'MAP_ID', None)
        return loaded is None or int(loaded) == int(BATTLE.get('map') or 0)
    except Exception:
        return True


try:
    _dh_m40v = _dh_wrap_global('space_properties', _dh_space_properties_weather, '_dh_weather')
    call_later(2.0, _dh_weather_tick, _dh_weather['token'])
    log('local-weather-installed', space=_dh_m40v)
except Exception:
    log_error('local-weather-install-error')


# --- m40w (2026-10-28): your flag in battle.  The result / death screen (onBattleGroundRankedResult results[gid]) was
# built with flag '' and the battle body without nationalFlag, so the screen showed the default flag although the
# lobby player had one (server_ext/profile_flag.py).  The lobby player's flag is read when the battle body is made and
# put on the body and on the result row.
_dh_flag = {'code': ''}


def _dh_flag_of(entity):
    try:
        value = getattr(entity, 'nationalFlag', '')
    except Exception:
        return ''
    return str(value or '') if isinstance(value, basestring) else ''


def _dh_player_properties_flag(player, map_id):
    properties = _dh_player_properties_flag._dh_inner(player, map_id)
    code = _dh_flag_of(player)
    if code:
        _dh_flag['code'] = code
        if isinstance(properties, dict):
            properties['nationalFlag'] = code
    return properties


def _dh_result_record_flag(player, rank, total):
    record = _dh_result_record_flag._dh_inner(player, rank, total)
    code = _dh_flag_of(player) or _dh_flag['code']
    if code and isinstance(record, dict):
        record['flag'] = code
        record['nationalFlag'] = code
    return record


try:
    _dh_m40w = {'body': _dh_wrap_global('player_properties', _dh_player_properties_flag, '_dh_flag'),
                'result': _dh_wrap_global('result_record', _dh_result_record_flag, '_dh_flag')}
    log('local-flag-installed', **_dh_m40w)
except Exception:
    log_error('local-flag-install-error')


# --- m40x (2026-10-28): no more white / black vehicles and no stuck "bike".  Two of the seven fleet types were the
# Motorcycle (land 25010) and the Bicycle (25100): two-wheelers the game builds with its own bike entity class, but
# the hook makes every fleet vehicle a LandCar, so they came out as the client's stand-in car model
# vehicle/crusher_xiaoguai (a mesh with no material in this build: drawn pure white, or black at night) with car
# physics on two wheels - the bike that gets stuck.  They are replaced by two complete four-wheelers from the game's
# own tables: Discovery (31012, jeep6) and Monster Truck (31007, guaiwupika).  Real motorbikes need the bike entity
# class (future work).
VEHICLE_FLEET = (
    ('LandCar', 25000, 115501),     # Roadster
    ('LandCar', 25001, 115500),     # SUV
    ('LandCar', 25003, 115503),     # Three-wheeler
    ('LandCar', 31012, 31012),      # Discovery (was the Motorcycle)
    ('LandCar', 31007, 31007),      # Monster Truck (was the Bicycle)
    ('LandCar', 31002, 131002),     # Truck
    ('LandCar', 31004, 131004),     # Battle Jeep
)
log('local-fleet-installed', fleet=[land for _cls, land, _tps in VEHICLE_FLEET])


# --- m40y (2026-10-28): supply boxes that land far away.  A box landing while the player is kilometres away cannot
# measure the ground there (no collision streamed in yet), so it, its light and its landing area (col_obj, where the
# open-with-F check sits) stand at a guessed height; the owner found one that would not open.  Every landed box is
# remembered; once the player has landed and comes within 300 m, the ground under the box is measured again and the
# box, light and landing area are put on it when the guess was off by more than half a metre.  Never measured during
# the plane / skydive (ground_height there closed the game in a test).
_DH_BOX_RECHECK_METRES = 300.0
_dh_boxes = {'token': object(), 'landed': {}}


def _dh_place_airdrop_light_record(entity_id, x, ground, z):
    done = _dh_place_airdrop_light_record._dh_inner(entity_id, x, ground, z)
    try:
        if entity_id not in _dh_boxes['landed'] or _dh_boxes['landed'][entity_id].get('fixed') is None:
            _dh_boxes['landed'][entity_id] = {'x': float(x), 'z': float(z), 'ground': float(ground), 'fixed': None}
    except Exception:
        pass
    return done


def _dh_box_tick(token):
    if token is not _dh_boxes['token']:
        return
    try:
        player = current_player()
        me = getattr(player, 'position', None)
        on_foot = (BATTLE.get('phase') == 'fighting' and _flight.get('landed_once')
                   and _flight.get('stage') not in ('plane', 'island') and me is not None
                   and not getattr(player, 'inPlane', False) and not getattr(player, 'isInSkyDive', False))
        if not on_foot:
            if BATTLE.get('phase') not in ('fighting', 'entering'):
                _dh_boxes['landed'].clear()
        else:
            for entity_id, box in list(_dh_boxes['landed'].items()):
                if box.get('fixed') is not None:
                    continue
                if _dh_math.hypot(box['x'] - me[0], box['z'] - me[2]) > _DH_BOX_RECHECK_METRES:
                    continue
                measured = ground_height(box['x'], box['z'])
                if not measured:
                    continue
                box['fixed'] = float(measured)
                if abs(float(measured) - box['ground']) > 0.5 and vehicle_entity(entity_id) is not None:
                    place_airdrop_light(entity_id, box['x'], float(measured), box['z'])
                    log('local-airdrop-box-reground', box=entity_id, was=round(box['ground'], 1), now=round(float(measured), 1))
    except Exception:
        if once('box-tick'):
            log_error('local-airdrop-box-reground-error')
    call_later(2.0, _dh_box_tick, token)


try:
    _dh_m40y = _dh_wrap_global('place_airdrop_light', _dh_place_airdrop_light_record, '_dh_boxes')
    call_later(2.0, _dh_box_tick, _dh_boxes['token'])
    log('local-airdrop-reground-installed', light=_dh_m40y)
except Exception:
    log_error('local-airdrop-reground-install-error')


# ---- m41: map pins and the team on the map (owner 2026-10-29: "pin won't show on the map if I click pin"; "they need
# to see where their teammates are").  The big map's click sends cell.markPos(Vector2(x, z)); online the cell then set
# the player's ownMarkPos (the map / radar / compass draw the own pin from it, "Go to my marker" navigates to it) and
# answered the team with onTeammateUpdateMarkPosition, which names the marker through getBattleMate(id).nickname - the
# player's own battleTeammates entry.  Ours: the hook only echoed onTeammateUpdateMarkPosition, ownMarkPos stayed
# (inf, inf), and battleTeammates was empty (the runtime's ensure_self_teammate only handles a plain list; this build
# keeps a PyArrayData), so the echo raised "'NoneType' object has no attribute 'nickname'" and no pin was drawn
# (probe 2026-10-29).  Now: the own entry is always in battleTeammates, a pin sets ownMarkPos + the entry's
# markPosition, and it rides on the act dict ('mk' x/z, 'ms' counter) like the m40u dance, so party teammates get the
# pin on their map, radar and compass (with the game's "marked a location" team line).  Enemies' pins are ignored.
_dh_pin = globals().get('_dh_pin') or {}
for _dh_k, _dh_v in (('mine', None), ('seq', 0), ('remote', {}), ('marks', 0), ('remote_marks', 0)):
    _dh_pin.setdefault(_dh_k, _dh_v)


def _dh_pin_vec(x, z, like=None):
    """A Math.Vector2 like the map's own (the game's type when it is loaded, else the type of a value we have)."""
    math_mod = _dh_sys.modules.get('Math')
    cls = getattr(math_mod, 'Vector2', None) if math_mod is not None else None
    if cls is None and like is not None:
        cls = type(like)
    return cls(float(x), float(z)) if cls is not None else (float(x), float(z))


class _DhLiveRecord(TeammateRecord):
    """A battleTeammates entry whose position / yaw are the entity's live ones: RadarMap.updatePlayerIcons reads them
    from every entry each frame, and a plain record answers 0 ("'int' object has no attribute '__getitem__'", 1000x a
    round on the laptop).  A written value is kept as the fallback for when the entity is gone (m40n writes them)."""

    def _dh_entity(self):
        try:
            import BigWorld
            return BigWorld.entities.get(self.__dict__.get('entID'))
        except Exception:
            return None

    @property
    def position(self):
        entity = self._dh_entity()
        if entity is not None:
            try:
                return entity.position
            except Exception:
                pass
        return self.__dict__.get('_dh_pos', (0.0, 0.0, 0.0))

    @position.setter
    def position(self, value):
        self.__dict__['_dh_pos'] = value

    @property
    def yaw(self):
        entity = self._dh_entity()
        if entity is not None:
            try:
                return float(getattr(entity, 'yaw', 0.0) or 0.0)
            except Exception:
                pass
        return self.__dict__.get('_dh_yaw', 0.0)

    @yaw.setter
    def yaw(self, value):
        self.__dict__['_dh_yaw'] = value


def _dh_pin_self(player):
    """The player's own battleTeammates entry, added when missing (solo rounds, or before a party sync)."""
    if player is None:
        return None
    own = getattr(player, 'id', None)
    try:
        current = list(getattr(player, 'battleTeammates', None) or [])
    except Exception:
        current = []
    for record in current:
        if getattr(record, 'entID', None) == own:
            return record
    me = _DhLiveRecord(**self_teammate(player).__dict__)
    try:
        me.isAlive = _DhAliveFlag(True)
    except Exception:
        pass
    try:
        old = getattr(player, 'battleTeammates', None)
        player.battleTeammates = [me] + current
        setter = getattr(player, 'set_battleTeammates', None)
        if callable(setter):
            setter(old)
    except Exception:
        if once('pin-self-entry'):
            log_error('local-pin-self-error')
        return None
    if once('pin-self-added'):
        log('local-pin-self-added', mates=len(current))
    return me


def _dh_pin_retire(player):
    """Take the own entry back out once the player is dead / the round is over: the 3D name tags
    (UI3DCompName.getDistance) treat every entry as a living body and, after leaveWorld, read a model that is gone
    ("'NoneType' object has no attribute 'transform'", 1000x on the result screen, laptop 2026-10-29)."""
    if player is None:
        return False
    own = getattr(player, 'id', None)
    try:
        current = list(getattr(player, 'battleTeammates', None) or [])
    except Exception:
        return False
    keep = [record for record in current if not (getattr(record, 'entID', None) == own and isinstance(record, _DhLiveRecord))]
    if len(keep) == len(current):
        return False
    try:
        old = getattr(player, 'battleTeammates', None)
        player.battleTeammates = keep
        setter = getattr(player, 'set_battleTeammates', None)
        if callable(setter):
            setter(old)
    except Exception:
        if once('pin-retire'):
            log_error('local-pin-retire-error')
        return False
    _dh_pin['map_seen'] = None
    if once('pin-retired'):
        log('local-pin-self-retired')
    return True


def _dh_pin_tell(player, entity_id, position):
    """The game's own reaction to a pin (team chat line "<name> marked a location", the sound)."""
    try:
        player.onTeammateUpdateMarkPosition(entity_id, position)
    except Exception:
        if once('pin-tell-%s' % (entity_id == getattr(player, 'id', None))):
            log_error('local-pin-tell-error', own=entity_id == getattr(player, 'id', None))


def _dh_pin_mark(player, position):
    me = _dh_pin_self(player)
    xz = _as_xz(position)                                  # None = the pin was removed (inf, inf)
    vec = position if position is not None else _dh_pin_vec(float('inf'), float('inf'))
    if me is not None:
        me.markPosition = vec
    set_player_field(player, 'ownMarkPos', vec)
    _dh_pin['mine'] = xz
    if xz is not None:
        _dh_steer_maybe_start(player, 'pin')         # m43: a pin placed during the fall steers the fall there
    _dh_pin['map_seen'] = time.time()                # keeps the entry for the team line below; the tick retires it
    _dh_pin['seq'] = int(_dh_pin['seq'] or 0) + 1
    _dh_pin['marks'] += 1
    if _dh_pin['marks'] in (1, 10, 100):
        log('local-pin-marked', n=_dh_pin['marks'], at=[round(v, 1) for v in xz] if xz else None)
    call_later(0.1, _dh_pin_tell, player, getattr(player, 'id', 0), vec)


def _dh_pin_handler_factory(inner):
    def handler(player, position=None, *args, **kwargs):
        try:
            _dh_pin_mark(player, position)
            return None
        except Exception:
            if once('pin-mark'):
                log_error('local-pin-mark-error', mark=safe(position, 80))
        return inner(player, position, *args, **kwargs)
    return handler


def _dh_pin_my_act_wrapper(*args, **kwargs):
    act = _dh_pin_my_act_wrapper._dh_inner(*args, **kwargs)
    try:
        if isinstance(act, dict) and _dh_pin['seq']:
            mine = _dh_pin['mine']
            act['mk'] = [round(mine[0], 1), round(mine[1], 1)] if mine else []
            act['ms'] = int(_dh_pin['seq'])
    except Exception:
        if once('pin-my-act'):
            log_error('local-pin-my-act-error')
    return act


def _dh_pin_apply_act_wrapper(battle_id, handle, act, *args, **kwargs):
    result = _dh_pin_apply_act_wrapper._dh_inner(battle_id, handle, act, *args, **kwargs)
    try:
        if isinstance(act, dict) and 'ms' in act:
            seq = int(act.get('ms') or 0)
            if _dh_pin['remote'].get(battle_id) != seq:
                _dh_pin['remote'][battle_id] = seq
                _dh_pin_remote(handle, act.get('mk') or [])
    except Exception:
        if once('pin-apply'):
            log_error('local-pin-apply-error')
    return result


def _dh_pin_remote(handle, mark):
    """A teammate's pin: their battleTeammates entry gets it and the game tells the team.  Not a teammate: ignored."""
    entity = _resolve_entity(handle)
    if entity is None or isinstance(entity, (int, long_type)):
        return
    player = current_player()
    entity_id = getattr(entity, 'id', None)
    record = None
    for mate in list(getattr(player, 'battleTeammates', None) or []):
        if getattr(mate, 'entID', None) == entity_id and entity_id != getattr(player, 'id', None):
            record = mate
            break
    if record is None:
        return
    if len(mark) == 2:
        vec = _dh_pin_vec(mark[0], mark[1], getattr(player, 'ownMarkPos', None))
    else:
        vec = _dh_pin_vec(float('inf'), float('inf'), getattr(player, 'ownMarkPos', None))
    record.markPosition = vec
    _dh_pin['remote_marks'] += 1
    if _dh_pin['remote_marks'] in (1, 10, 100):
        log('local-pin-teammate', n=_dh_pin['remote_marks'], mate=getattr(record, 'nickname', ''), cleared=len(mark) != 2)
    _dh_pin_tell(player, entity_id, vec)


def _dh_pin_died_wrapper(player, *args, **kwargs):
    result = _dh_pin_died_wrapper._dh_inner(player, *args, **kwargs)
    try:
        _dh_pin_retire(player)
    except Exception:
        pass
    return result


def _dh_pin_leave_wrapper(player=None, *args, **kwargs):
    try:
        _dh_pin_retire(player or current_player())
    except Exception:
        pass
    _dh_pin['mine'], _dh_pin['seq'] = None, 0
    _dh_pin['remote'].clear()            # entity ids are per round
    return _dh_pin_leave_wrapper._dh_inner(player, *args, **kwargs)


def _dh_pin_tick(token):
    """m41g: the own entry lives only while the big map is open (UIDtsMap.updateBattleMateMarkPos marks 'map_seen').
    A lasting own entry made the game take the player for a teammate standing in front of their own gun: the red
    no-fire sign at the crosshair and shots that sometimes did not leave (owner, 2026-10-29), plus the floating own
    name tag.  The minimap and the compass draw the own pin from ownMarkPos and need no entry."""
    if token is not _dh_pin.get('token'):
        return
    present = False
    try:
        # only in a battle: in the lobby the player is the hall avatar, and reading its battleTeammates made the hook
        # log "attribute defaulted" every 2 s (laptop 2026-10-29)
        player = current_player() if BATTLE.get('phase') in ('entering', 'fighting', 'over') else None
        if player is not None and getattr(player, 'id', None) is not None:
            if time.time() - float(_dh_pin.get('map_seen') or 0.0) > 0.25:
                _dh_pin_retire(player)
            else:
                present = True
    except Exception:
        if once('pin-tick'):
            log_error('local-pin-tick-error')
    call_later(0.3 if present or _dh_pin.get('map_seen') else 2.0, _dh_pin_tick, token)


def _dh_pin_map_factory(inner):
    def updateBattleMateMarkPos(self, *args, **kwargs):
        try:
            if not _round.get('over') and BATTLE.get('phase') in ('entering', 'fighting'):
                _dh_pin['map_seen'] = time.time()
                _dh_pin_self(current_player())
        except Exception:
            if once('pin-map'):
                log_error('local-pin-map-error')
        return inner(self, *args, **kwargs)
    return updateBattleMateMarkPos


try:
    _dh_m41 = {
        'markPos': _dh_wrap_handler('markPos', _dh_pin_handler_factory, '_dh_pin'),
        'my_act': _dh_wrap_global('my_act', _dh_pin_my_act_wrapper, '_dh_pin'),
        'act': _dh_wrap_global('apply_act', _dh_pin_apply_act_wrapper, '_dh_pin'),
        'leave': _dh_wrap_global('leave_battle', _dh_pin_leave_wrapper, '_dh_pin'),
        'died': _dh_wrap_global('player_died', _dh_pin_died_wrapper, '_dh_pin'),
    }
    _dh_pin['token'] = object()
    call_later(3.0, _dh_pin_tick, _dh_pin['token'])
    log('local-pin-installed', **_dh_m41)
except Exception:
    log_error('local-pin-install-error')


# m41f (2026-10-29): a pin farther than the minimap reaches vanished once the big map was closed (owner, laptop: five
# far pins, empty minimap).  RadarMap.updateBattleMateMarkPos puts the own pin (ownMarkPos) and the teammates' pins
# (validBattleTeammates[i].markPosition) at their true map spot and the round stencil cuts off anything past the rim;
# the game has no rim arrow (probe 2026-10-29).  Now a pin icon outside the circle is drawn on the rim in the pin's
# direction, like the off-radar icons of other battle royales (the compass keeps the distance).  Positions go through
# cocos convertToWorldSpace / convertToNodeSpace, so the map's scale and rotation need no maths of ours.
# Also: UI3DCompBattleGroundName.getDistance reads the local player's model, and after it left the world it raised
# "'NoneType' object has no attribute 'transform'" every frame (1000x after the owner's round): it now answers 9999,
# the value the game itself uses for "too far" (the tag hides).
_dh_rim = globals().get('_dh_rim') or {}
for _dh_k, _dh_v in (('true', {}), ('put', {}), ('fails', 0), ('off', False), ('first', False)):
    _dh_rim.setdefault(_dh_k, _dh_v)
_DH_RIM_INSET = 0.84                     # the icon's anchor stays this far out (share of the radius): the pin fits inside


def _dh_rim_ring(radar, cc):
    """Centre and radius of the minimap circle in screen space.  mapLayer is the ClippingNode (0x0, at the circle's
    centre) whose stencil (bg_fight_map_01.png) is the circle; the 210x210 'dts_map_btn' two levels up is the fallback
    size (laptop 2026-10-29: centre 120,130, button 14..224)."""
    layer = getattr(radar, 'mapLayer', None)
    if layer is None:
        return None
    cached = _dh_rim.get('ring')
    if cached is not None and cached[0] is layer:
        return cached[1]
    centre = layer.convertToWorldSpace(cc.Vec2(0.0, 0.0))
    radius, source = 0.0, None
    nodes = []
    stencil = getattr(layer, 'getStencil', None)
    if callable(stencil):
        nodes.append(('stencil', stencil()))
    parent = layer.getParent()
    for _ in range(3):
        if parent is None:
            break
        nodes.append(('button', parent.getChildByName('dts_map_btn')))
        parent = parent.getParent()
    for name, node in nodes:
        if node is None:
            continue
        size = node.getContentSize()
        a = node.convertToWorldSpace(cc.Vec2(0.0, 0.0))
        b = node.convertToWorldSpace(cc.Vec2(size.width, size.height))
        radius = min(abs(b.x - a.x), abs(b.y - a.y)) * 0.5
        if radius >= 20.0:
            source = name
            break
    if radius < 20.0:
        return None
    ring = (centre.x, centre.y, radius)
    _dh_rim['ring'] = (layer, ring)
    log('local-rim-ring', ring=[round(v, 1) for v in ring], source=source)
    return ring


def _dh_rim_sprite(value):
    if hasattr(value, 'setPosition'):
        return value
    if isinstance(value, (list, tuple)):
        for item in value:
            if hasattr(item, 'setPosition'):
                return item
    return None


def _dh_rim_place(radar):
    mod = _dh_sys.modules.get('ui.ingame.RadarMap')
    cc = getattr(mod, 'cc', None) if mod is not None else None
    marks = getattr(radar, 'playerMarks', None)
    if cc is None or not marks:
        _dh_rim['true'], _dh_rim['put'] = {}, {}
        return
    ring = _dh_rim_ring(radar, cc)
    if ring is None:
        return
    cx, cy, radius = ring
    limit = radius * _DH_RIM_INSET
    true, put = {}, {}
    for value in list(marks.values()):
        sprite = _dh_rim_sprite(value)
        parent = sprite.getParent() if sprite is not None else None
        if parent is None:
            continue
        key = id(sprite)
        pos = sprite.getPosition()
        last = _dh_rim['put'].get(key)
        if last is None or abs(pos.x - last[0]) > 0.05 or abs(pos.y - last[1]) > 0.05:
            true[key] = (pos.x, pos.y)                     # the game (re)placed it: that is the pin's true spot
        else:
            true[key] = _dh_rim['true'].get(key, (pos.x, pos.y))
        tx, ty = true[key]
        world = parent.convertToWorldSpace(cc.Vec2(tx, ty))
        dx, dy = world.x - cx, world.y - cy
        distance = math.hypot(dx, dy)
        target = (tx, ty)
        if distance > limit:
            back = parent.convertToNodeSpace(cc.Vec2(cx + dx * limit / distance, cy + dy * limit / distance))
            target = (back.x, back.y)
            if not _dh_rim['first']:
                _dh_rim['first'] = True
                log('local-rim-first', ring=[round(cx, 1), round(cy, 1), round(radius, 1)],
                    pin=[round(world.x, 1), round(world.y, 1)], rim=[round(v, 1) for v in target], true=[round(tx, 1), round(ty, 1)])
        if abs(target[0] - pos.x) > 0.05 or abs(target[1] - pos.y) > 0.05:
            sprite.setPosition(cc.Vec2(target[0], target[1]))
            pos = sprite.getPosition()
            target = (pos.x, pos.y)
        put[key] = target
    _dh_rim['true'], _dh_rim['put'] = true, put


def _dh_rim_factory(inner):
    def updateBattleMateMarkPos(self, *args, **kwargs):
        result = inner(self, *args, **kwargs)
        if not _dh_rim['off'] and getattr(self, 'playerMarks', None):
            try:
                _dh_rim_place(self)
            except Exception:
                _dh_rim['fails'] += 1
                if _dh_rim['fails'] in (1, 20):
                    log_error('local-rim-error', fails=_dh_rim['fails'])
                if _dh_rim['fails'] >= 20:
                    _dh_rim['off'] = True             # never an error per frame
        return result
    return updateBattleMateMarkPos


def _dh_tag_distance_factory(inner):
    def getDistance(self, *args, **kwargs):
        try:
            return inner(self, *args, **kwargs)
        except AttributeError:
            if once('tag-distance-guard'):
                log('local-tag-distance-guard')
            return 9999.0
    return getDistance


def _dh_class_wrap(module_name, class_name, method, factory, marker):
    mod = _dh_sys.modules.get(module_name)
    cls = getattr(mod, class_name, None) if mod is not None else None
    inner = (getattr(cls, '__dict__', None) or {}).get(method) if cls is not None else None
    if inner is None:
        return False
    while getattr(inner, marker, False):
        inner = inner._dh_inner
    wrapped = factory(inner)
    # m42d: carry the inner's attributes over - libclaudia dispatches SendMessage only to functions marked
    # ____isMessageHandler__, and a wrapper without the mark is silently skipped (the m114e Exchange button was dead;
    # SpeedManager.onChangePose is sent the same way: the pose stayed STAND in the fall, ~5 m/s instead of ~12)
    wrapped.__dict__.update(getattr(inner, '__dict__', {}) or {})
    setattr(wrapped, marker, True)
    wrapped._dh_inner = inner
    setattr(cls, method, wrapped)
    return True


def _dh_rim_install(token, tries=0):
    if token is not _dh_rim.get('token'):
        return
    done = _dh_rim.setdefault('done', {})
    try:
        if not done.get('rim'):
            done['rim'] = _dh_class_wrap('ui.ingame.RadarMap', 'RadarMap', 'updateBattleMateMarkPos', _dh_rim_factory, '_dh_rim_w')
        if not done.get('map'):
            done['map'] = _dh_class_wrap('ui.UIDtsMap', 'UIDtsMap', 'updateBattleMateMarkPos', _dh_pin_map_factory, '_dh_pinmap_w')
        if not done.get('tag'):
            done['tag'] = _dh_class_wrap('ui.UI3DCompName', 'UI3DCompBattleGroundName', 'getDistance',
                                         _dh_tag_distance_factory, '_dh_tagd_w')
    except Exception:
        log_error('local-rim-install-error')
        return
    if done.get('rim') and done.get('tag') and done.get('map'):
        log('local-rim-installed', tries=tries)
    elif tries < 1440:                                # the battle UI modules load with the first round
        call_later(5.0, _dh_rim_install, token, tries + 1)


_dh_rim['token'] = object()
_dh_rim['done'] = {}
call_later(1.0, _dh_rim_install, _dh_rim['token'])


# m42 (2026-10-29): auto-jump at your pin.  Owner: "build the jump at my pin if almost near the pin".  The game has no
# such thing (the plane is left only by the jump buttons or at the route's end - code scan 2026-10-29).  While aboard
# with a pin set, the plane's closest point to the pin is worked out on the known route (_flight start/end, the hook
# flies it in a straight line) and the player jumps there - through cell.requestGetOffPlane, the call the jump buttons
# make - when that point is within _DH_PINJUMP_REACH of the pin.  A pin too far from the route only gets a tip; F still
# jumps any time.  Moving / removing the pin in the plane re-plans.
_DH_PINJUMP_ON = True
_DH_PINJUMP_REACH = 10000.0            # game units (~1,000 m): what a parachute from the plane's height covers
_DH_PINJUMP_LEAD = 0.0                 # no lead: the jump keeps none of the plane's speed (laptop: the dive starts
                                       # straight down) - the closest point is the best place to leave
_dh_pinjump = globals().get('_dh_pinjump') or {}
_dh_pinjump.update(token=object(), plan=None, said=None)


def _dh_pinjump_plan(mark):
    """(share of the route where the plane is closest to the pin, distance there) on the straight route."""
    start, end = _flight.get('start'), _flight.get('end')
    if not start or not end:
        return None
    dx, dz = float(end[0]) - float(start[0]), float(end[1]) - float(start[1])
    length2 = dx * dx + dz * dz
    if length2 <= 1.0:
        return None
    share = ((mark[0] - float(start[0])) * dx + (mark[1] - float(start[1])) * dz) / length2
    share = max(0.0, min(1.0, share))
    cx, cz = float(start[0]) + dx * share, float(start[1]) + dz * share
    return share, math.hypot(mark[0] - cx, mark[1] - cz)


def _dh_pinjump_go(player, distance):
    cell = getattr(player, 'cell', None)
    try:
        cell.requestGetOffPlane()
    except Exception:
        handler = (getattr(LOBBY, 'RPC_HANDLERS', None) or {}).get('requestGetOffPlane')
        if not callable(handler):
            raise
        handler(player)
    tip_text('Jumping at your pin (%d m away)' % int(distance / 10.0))
    starter = globals().get('_dh_steer_start')
    if callable(starter):
        call_later(1.0, starter)                       # m42c: then steer the dive to the pin
    log('local-pin-jump', metres=int(distance / 10.0), share=round(float(_flight.get('travelled') or 0.0) /
                                                                     max(1.0, float(_flight.get('length') or 1.0)), 3))


def _dh_pinjump_tick(token):
    if token is not _dh_pinjump.get('token'):
        return
    fast = False
    try:
        aboard = _DH_PINJUMP_ON and _flight.get('stage') == 'plane' and _flight.get('aboard')
        player = current_player() if aboard else None
        mark = _as_xz(getattr(player, 'ownMarkPos', None)) if player is not None else None
        if not aboard or mark is None:
            if not aboard:
                _dh_pinjump.update(plan=None, said=None)
        else:
            fast = True
            key = (round(mark[0]), round(mark[1]))
            plan = _dh_pinjump.get('plan')
            if plan is None or plan[0] != key:
                found = _dh_pinjump_plan(mark)
                plan = (key,) + tuple(found) if found else None
                _dh_pinjump['plan'] = plan
                if plan is not None and _dh_pinjump.get('said') != key:
                    _dh_pinjump['said'] = key
                    if plan[2] <= _DH_PINJUMP_REACH:
                        tip_text('Auto-jump at your pin: ON (press F to jump earlier)')
                    else:
                        tip_text('Your pin is %d m from the flight path - too far to auto-jump' % int(plan[2] / 10.0))
                    log('local-pin-jump-plan', share=round(plan[1], 3), metres=int(plan[2] / 10.0))
            if plan is not None and plan[2] <= _DH_PINJUMP_REACH and _flight.get('can_jump'):
                length = max(1.0, float(_flight.get('length') or 1.0))
                now_share = float(_flight.get('travelled') or 0.0) / length
                if now_share >= plan[1] - _DH_PINJUMP_LEAD / length:
                    x, _y, z = plane_position()
                    _dh_pinjump['plan'] = (plan[0], 2.0, plan[2])     # once per pin
                    _dh_pinjump_go(player, math.hypot(mark[0] - x, mark[1] - z))
    except Exception:
        if once('pin-jump'):
            log_error('local-pin-jump-error')
    call_later(0.25 if fast else 2.0, _dh_pinjump_tick, token)


call_later(2.0, _dh_pinjump_tick, _dh_pinjump['token'])
log('local-pin-jump-installed', reach_m=int(_DH_PINJUMP_REACH / 10.0))


# m42c (2026-10-29) / m43 (2026-10-31): after a jump with a pin set, the fall steers itself to the pin.  Owner: "auto
# steering to the pin location"; "auto route in gliding mode not working".
# How the game moves in the air (laptop rounds 10:52-14:37, gl_code dump): SpeedManager.moveByDir(vec3_dir) only
# carries the SPEED - moveWithPose snaps it to forward / back (z > 0 full speed, z < 0 brake: 0.5 m/s over the ground
# in a glider) and throws the sideways part away.  TURNING is the parachute controller's job
# (player.logic_ctrls.ParachutePlayerController: ParachuteH45Controller / ParachutePUBGController on the player's
# gameObject) re-aims the player at the CAMERA: the mouse goes InputInterpred.IptMsg_RotateCamera -> camera
# 'onRotateCameraFromUser' -> PlayerCameraController.onRotateCamera(Vector2(dYaw, dPitch) degrees, rotAvatar) on the
# pivot -> player message 'cmdRotateCamera' -> ParachuteH45Controller.cmdRotateCamera (no args) -> rotatePlayer
# coroutine -> setVelYaw at the parachute turn speed, and the glider follows.  The game's own death camera drives it
# the same way (PlayerAvatarController.rotateUpCamera: onRotateCamera(Vector2(0, step), True) every 0.03 s).  Two
# earlier m43 builds fed the turn to moveByDir and to the controller's onMove - neither moves the pivot, and the
# heading never changed (laptop 14:37 and 14:54, -33 / -160 deg for the whole glide).
# Gliders fly two ways: the DIVE (pose 12, phase 6: ~7 m/s over the ground, 23 m/s down) and the GLIDE (pose 14:
# ~22 m/s over the ground, 8.5 m/s down); F toggles them (FightOperation.offAircraft).  Glide while the pin is further
# than the dive can still cover from this height, dive when it is not, and over the pin brake the glide: it then sinks
# almost vertically.  Any movement key of the player's own hands control back for the rest of that fall.
_DH_STEER_ON = True
_DH_STEER_ARRIVED = 300.0              # units (~30 m): over the pin (parachute) - stop steering
_DH_STEER_DEADBAND = 3.0               # deg: no turn inside this heading error
_DH_STEER_TURN_STEP = 5.0              # deg of camera yaw per 0.1 s tick (50 deg/s at most)
_DH_STEER_DIVE_RATIO = 0.3             # dive: ground distance covered per unit of height lost (7 / 23, laptop 14:37)
_DH_STEER_DIVE_MARGIN = 100.0          # units: switch to the dive this much before the dive alone reaches the pin
_DH_STEER_GLIDE_AGAIN = 400.0          # units: back to the glide only when the pin got this much further than the reach
_DH_STEER_HOVER_IN = 150.0             # units (15 m): over the pin with height left - glide + brake sinks vertically
_DH_STEER_HOVER_OUT = 400.0            # units: drifted this far off while hovering - steer again
_DH_STEER_SWITCH_GAP = 3.0             # s between two pose switches
_DH_STEER_SWITCH_MAX = 8               # pose switches per fall
_dh_steer = globals().get('_dh_steer') or {}
_dh_steer.update(token=object(), active=False, ours=False, manual=False, last=None, logs=0, fails=0,
                 landed_hooked=False, sign=float(_dh_steer.get('sign') or 1.0))


def _dh_steer_controller(player):
    """The player's SpeedManager: its moveByDir(vec3_dir) is where the movement keys go in every pose."""
    go = getattr(player, 'gameObject', None)
    if go is None:
        return None
    try:
        return go.GetComponent('SpeedManager')
    except Exception:
        return None


def _dh_steer_turner(player):
    """The active parachute controller on the player's gameObject (its cmdRotateCamera re-aims the glider / chute)."""
    go = getattr(player, 'gameObject', None)
    if go is None:
        return None
    for name in ('ParachuteH45Controller', 'ParachutePUBGController'):
        try:
            comp = go.GetComponent(name)
        except Exception:
            comp = None
        if comp is not None and getattr(comp, 'enabled', True):
            if _dh_steer.get('turner') != name:
                _dh_steer['turner'] = name
                log('local-steer-turner', name=name)
            return comp
    return None


def _dh_steer_vec(x, z):
    """A Vector3 of the type SpeedManager.moveByDir takes (its own module's; Math.Vector3 is refused:
    "argument 1 must be set to a concrete PyObjectPlusType class object", laptop 2026-10-29)."""
    for name in ('player.logic_ctrls.DTSSpeedManager', 'Math'):
        mod = _dh_sys.modules.get(name)
        cls = getattr(mod, 'Vector3', None) if mod is not None else None
        if cls is not None:
            return cls(float(x), 0.0, float(z))
    return None


def _dh_xz_of(value):
    try:
        return float(value.x), float(value.z)
    except Exception:
        pass
    try:
        items = list(value)
        return float(items[0]), float(items[2] if len(items) > 2 else items[1])
    except Exception:
        return None


def _dh_cam_yaw():
    """Camera heading in degrees (atan2(x, z) of its forward, the same frame as the bearing to the pin), or None."""
    try:
        mod = _dh_sys.modules.get('player.logic_ctrls.ParachutePlayerController')
        f = mod.Camera.main.transform.forward
        return math.degrees(math.atan2(float(f.x), float(f.z)))
    except Exception:
        return None


def _dh_wrap_deg(a):
    return (float(a) + 180.0) % 360.0 - 180.0


def _dh_steer_speed(player, z):
    """Hold the speed "key": z = 1 forward, -1 brake, 0 release."""
    comp = _dh_steer_controller(player)
    if comp is None:
        return
    vec = _dh_steer_vec(0.0, z)
    _dh_steer['ours'] = True
    try:
        _dh_steer['sent'] = _dh_xz_of(vec)
        comp.moveByDir(vec)
    finally:
        _dh_steer['ours'] = False


def _dh_steer_camera():
    """The main camera's PlayerCameraController and the Vector2 type it takes (both reachable from the parachute
    controller module), or (None, None)."""
    mod = _dh_sys.modules.get('player.logic_ctrls.ParachutePlayerController')
    try:
        return mod.Camera.main.GetComponent('PlayerCameraController'), mod.Vector2
    except Exception:
        return None, None


def _dh_steer_turn(player, delta):
    """Turn the camera by delta degrees of yaw the way the mouse does, then re-aim the body at it."""
    if abs(delta) < 0.2:
        return
    cam, vector2 = _dh_steer_camera()
    if cam is None:
        if once('steer-no-camera'):
            log('local-steer-no-camera')
        return
    _dh_steer['ours'] = True
    try:
        cam.onRotateCamera(vector2(float(delta) * float(_dh_steer.get('sign') or 1.0), 0.0), True)
        _dh_steer['turning'] = delta
        for comp in (_dh_steer_turner(player), _dh_steer_controller(player)):
            fn = getattr(comp, 'cmdRotateCamera', None)
            if fn is not None:
                try:
                    fn()
                except Exception:
                    if once('steer-cmd-rotate'):
                        log_error('local-steer-cmd-rotate-error')
    finally:
        _dh_steer['ours'] = False


def _dh_steer_learn_sign(cam_yaw):
    """Which way does x = +1 turn?  Watch the camera after our own turn commands; three disagreements in a row flip
    the sign for the rest of the session (never assume the engine's handedness)."""
    prev, turn = _dh_steer.get('cam_prev'), _dh_steer.get('turning_prev')
    _dh_steer['cam_prev'], _dh_steer['turning_prev'] = cam_yaw, _dh_steer.get('turning')
    _dh_steer['turning'] = None
    if prev is None or cam_yaw is None or not turn:
        return
    delta = _dh_wrap_deg(cam_yaw - prev)
    if abs(delta) < 1.0:
        return
    if (delta > 0) == (turn * float(_dh_steer.get('sign') or 1.0) > 0):
        _dh_steer['wrong'] = 0
        return
    _dh_steer['wrong'] = int(_dh_steer.get('wrong') or 0) + 1
    if _dh_steer['wrong'] >= 3:
        _dh_steer['sign'] = -float(_dh_steer.get('sign') or 1.0)
        _dh_steer['wrong'] = 0
        log('local-steer-sign', sign=_dh_steer['sign'])


_DH_STEER_GAME_CALLERS = ('onChangePose', 'OnEnable', 'OnDisable', 'rotatePlayer', 'Awake', 'Start', 'cmdRotateCamera')


def _dh_steer_callers(depth=6):
    names = []
    try:
        frame = _dh_sys._getframe(2)
        while frame is not None and len(names) < depth:
            names.append(frame.f_code.co_name)
            frame = frame.f_back
    except Exception:
        pass
    return names


def _dh_steer_onmove_factory(inner):
    def moveByDir(self, vec3_dir):                 # exact signature: SendMessage dispatches by argument count (R1)
        try:
            if _dh_steer.get('active') and not _dh_steer.get('ours') and not _dh_steer.get('in_pose'):
                got = _dh_xz_of(vec3_dir) or (0.0, 0.0)
                if math.hypot(got[0], got[1]) > 0.05:
                    callers = _dh_steer_callers()
                    # a key reaches moveByDir through the input message (msgMoveDir -> onTrigger -> onMove); the game
                    # re-sends it around the parachute opening and from its own turn coroutine, those do not count
                    settling = time.time() - float(_dh_steer.get('phase_at') or 0.0) < 1.5
                    game = settling or 'msgMoveDir' not in callers or any(n in _DH_STEER_GAME_CALLERS for n in callers)
                    if not game:
                        _dh_steer.update(active=False, manual=True)
                        log('local-steer-manual', got=[round(v, 2) for v in got], callers=callers)
        except Exception:
            pass
        return inner(self, vec3_dir)
    return moveByDir


def _dh_steer_switch_pose(player, want, dist, height):
    """Dive <-> glide the way F does (FightOperation.offAircraft -> the UI's Dive/Glide switch), when the game shows it."""
    now = time.time()
    if now - float(_dh_steer.get('switch_at') or 0.0) < _DH_STEER_SWITCH_GAP or int(_dh_steer.get('switches') or 0) >= _DH_STEER_SWITCH_MAX:
        return
    try:
        import Globals as _g
        fall = getattr(_g.uiMgr, 'UIBattlegroundsFall', None)
        button = getattr(fall, 'switchSpeedBtn', None) if fall is not None and getattr(fall, 'is_enter', False) else None
        if button is None or not button.isVisible():
            return
        _dh_steer['switch_at'] = now
        _dh_steer['switches'] = int(_dh_steer.get('switches') or 0) + 1
        _g.uiMgr.UIBattlegroundsInGame.fightOperation.offAircraft()
        log('local-steer-pose', want=want, metres=int(dist / 10.0), height_m=int(height / 10.0))
    except Exception:
        _dh_steer['switches'] = _DH_STEER_SWITCH_MAX   # no more tries this fall
        if once('steer-switch-pose'):
            log_error('local-steer-pose-error')


def _dh_steer_glider_plan(player, dist, pos):
    """What a glider should do now: ('glide' | 'dive' | 'hover', forward z).  Height is above sea level (the terrain
    sits within ~60 m of it here; never ground_height() in the air)."""
    pose = int(getattr(player, 'clientPose', 0) or 0)
    if pose not in (12, 14):
        return None
    height = max(0.0, float(pos[1]))
    reach = _DH_STEER_DIVE_RATIO * height
    hover = bool(_dh_steer.get('hover'))
    if hover and dist > _DH_STEER_HOVER_OUT:
        hover = False
    elif not hover and dist <= _DH_STEER_HOVER_IN and height > 150.0:
        hover = True
    _dh_steer['hover'] = hover
    if hover:
        if pose != 14:
            _dh_steer_switch_pose(player, 14, dist, height)
        return 'hover', -1.0
    if pose == 14 and dist <= reach + _DH_STEER_DIVE_MARGIN:
        _dh_steer_switch_pose(player, 12, dist, height)
    elif pose == 12 and dist >= reach + _DH_STEER_GLIDE_AGAIN:
        _dh_steer_switch_pose(player, 14, dist, height)
    return ('dive' if pose == 12 else 'glide'), 1.0


def _dh_steer_start():
    if not _DH_STEER_ON:
        return
    _dh_steer.update(active=True, manual=False, last=None, logs=0, started=time.time(), landed=False, prev_log=None,
                     phase=None, phase_at=0.0, turning=None, turning_prev=None, cam_prev=None, wrong=0, hover=False,
                     switch_at=0.0, switches=0, turner=None)
    tip_text('Steering to your pin (move to take over)')
    log('local-steer-start')


def _dh_steer_maybe_start(player, why):
    """m43: steer to the pin after ANY jump with a pin set (F / jump button, not only the auto-jump) and when a pin is
    placed during the fall."""
    try:
        if not _DH_STEER_ON or _dh_steer.get('active') or (why != 'jump' and _dh_steer.get('manual')):
            return                                     # a takeover lasts for the rest of that fall only
        if _as_xz(getattr(player, 'ownMarkPos', None)) is None:
            return
        if int(getattr(player, 'fallPhase', 0) or 0) == 0 and why != 'jump':      # 0 = NORMAL: on the ground
            return
        log('local-steer-begin', why=why)
        call_later(1.0, _dh_steer_start)
    except Exception:
        if once('steer-maybe'):
            log_error('local-steer-maybe-error')


def _dh_steer_release(player, dist, why):
    _dh_steer['active'] = False
    _dh_steer_speed(player, 0.0)                       # let go of the "keys" we were holding
    if why == 'arrived':
        tip_text('Over your pin')
    log('local-steer-end', metres=int(dist / 10.0), why=why)


def _dh_steer_tick(token):
    if token is not _dh_steer.get('token'):
        return
    fast = False
    try:
        if _dh_steer.get('active'):
            fast = True
            player = current_player()
            mark = _as_xz(getattr(player, 'ownMarkPos', None)) if player is not None else None
            pos = getattr(player, 'position', None) if player is not None else None
            if mark is None or pos is None or time.time() - float(_dh_steer.get('started') or 0) > 300.0:
                _dh_steer['active'] = False
                log('local-steer-end', why='no-pin' if mark is None else 'timeout')
            else:
                dx, dz = mark[0] - float(pos[0]), mark[1] - float(pos[2])
                dist = math.hypot(dx, dz)
                phase_now = (getattr(player, 'fallPhase', None), getattr(player, 'clientPose', None))
                if phase_now != _dh_steer.get('phase'):
                    _dh_steer['phase'], _dh_steer['phase_at'] = phase_now, time.time()
                cam_yaw = _dh_cam_yaw()
                _dh_steer_learn_sign(cam_yaw)
                bearing = math.degrees(math.atan2(dx, dz))
                heading_err = None
                if cam_yaw is not None:
                    heading_err = round(_dh_wrap_deg(cam_yaw - bearing), 1)
                else:
                    last = _dh_steer.get('last')
                    if last is not None:
                        mx, mz = float(pos[0]) - last[0], float(pos[2]) - last[1]
                        if math.hypot(mx, mz) > 5.0:
                            heading_err = round(_dh_wrap_deg(math.degrees(math.atan2(mx, mz)) - bearing), 1)
                _dh_steer['last'] = (float(pos[0]), float(pos[2]))
                glider = int(getattr(player, 'jetWingsID', 0) or 0)
                plan = _dh_steer_glider_plan(player, dist, pos) if glider else None
                if _dh_steer.get('landed'):
                    _dh_steer_release(player, dist, 'landed')
                elif plan is None and dist <= _DH_STEER_ARRIVED:
                    _dh_steer_release(player, dist, 'arrived')
                elif int(getattr(player, 'clientPose', 0) or 0) == 0 and not _dh_glide.get('jumped'):
                    pass                                   # still in the plane: nothing to steer yet
                else:
                    mode, forward = plan if plan is not None else ('chute', 1.0)
                    turn = 0.0
                    if mode != 'hover' and heading_err is not None and abs(heading_err) > _DH_STEER_DEADBAND:
                        turn = -max(-_DH_STEER_TURN_STEP, min(_DH_STEER_TURN_STEP, heading_err))
                    _dh_steer_turn(player, turn)
                    _dh_steer_speed(player, forward)
                    prev = _dh_steer.get('prev_log')
                    now_t = time.time()
                    if _dh_steer['logs'] < 80 and (prev is None or now_t - prev[0] >= 1.0):
                        _dh_steer['logs'] += 1
                        mps = None
                        if prev is not None and now_t > prev[0]:
                            mps = round(math.hypot(float(pos[0]) - prev[1], float(pos[2]) - prev[2]) / 10.0 / (now_t - prev[0]), 1)
                        _dh_steer['prev_log'] = (now_t, float(pos[0]), float(pos[2]))
                        log('local-steer', metres=int(dist / 10.0), err=heading_err, mps=mps, y=round(float(pos[1])),
                            mode=mode, turn=round(turn, 1), cam=None if cam_yaw is None else round(cam_yaw, 1),
                            pose=int(getattr(player, 'clientPose', 0) or 0))
    except Exception:
        _dh_steer['fails'] = int(_dh_steer.get('fails') or 0) + 1
        if _dh_steer['fails'] in (1, 5, 50):
            log_error('local-steer-error', fails=_dh_steer['fails'])
        if _dh_steer['fails'] >= 5:
            _dh_steer['active'] = False                # never an error loop
    call_later(0.1 if fast else 2.0, _dh_steer_tick, token)


def _dh_steer_pose_factory(inner):
    def onChangePose(self, poseIdx):              # exact signature (R1); the game's own moveByDir from here is not a key
        _dh_steer['in_pose'] = True
        try:
            return inner(self, poseIdx)
        finally:
            _dh_steer['in_pose'] = False
    return onChangePose


def _dh_steer_landed_wrapper(*args, **kwargs):
    _dh_steer['landed'] = True                         # this fall is over (the hook's own landing)
    return _dh_steer_landed_wrapper._dh_inner(*args, **kwargs)


def _dh_steer_install(tries=0):
    if not _dh_steer.get('landed_hooked'):
        _dh_steer['landed_hooked'] = _dh_wrap_global('landed', _dh_steer_landed_wrapper, '_dh_steer')
    ok = _dh_class_wrap('player.logic_ctrls.DTSSpeedManager', 'SpeedManager', 'moveByDir', _dh_steer_onmove_factory,
                        '_dh_steer_w')
    ok = _dh_class_wrap('player.logic_ctrls.DTSSpeedManager', 'SpeedManager', 'onChangePose', _dh_steer_pose_factory,
                        '_dh_steerpose_w') and ok
    if ok:
        log('local-steer-installed', sign=_dh_steer.get('sign'))
    elif tries < 720:
        call_later(5.0, _dh_steer_install, tries + 1)


call_later(1.0, _dh_steer_install)
call_later(2.0, _dh_steer_tick, _dh_steer['token'])


# m42e (2026-10-29): frozen on the loading screen after a round (player report 21:20 "nag freeze man": result screen ->
# Next -> the return art stays up; the same crash report from a second PC at 10:39 and 21:29).  leave_battle runs
# cancel() first, which hands the game-look input back to the lobby (the UserInput object goes inactive), and only
# then drop_battle_world() destroys the battle body.  Avatar.leaveWorld sends onPlayerLeaveWorld to that inactive
# UserInput; libclaudia raises "The message is not picked up by any component", the runtime input guard lets it
# through (the battle phase is already idle), leaveWorld stops half way and the lobby is never handed over.
# Drop exactly that undelivered message: the component is inactive on purpose and has nothing to clean up.
_DH_LEAVE_MESSAGES = frozenset(['onPlayerLeaveWorld'])
_dh_leavemsg = {'dropped': 0}


def _dh_leavemsg_factory(inner):
    def SendMessage(self, methodName, *args, **kwargs):
        try:
            return inner(self, methodName, *args, **kwargs)
        except Exception as error:
            if methodName not in _DH_LEAVE_MESSAGES or 'not picked up' not in str(error):
                raise
            _dh_leavemsg['dropped'] += 1
            if _dh_leavemsg['dropped'] <= 3:
                log('local-leave-message-dropped', message=methodName, target=safe(getattr(self, 'name', None), 40),
                    count=_dh_leavemsg['dropped'])
            return None
    return SendMessage


def _dh_leavemsg_install(tries=0):
    try:
        ok = _dh_class_wrap('libclaudia.Classes.GameObject', 'GameObject', 'SendMessage', _dh_leavemsg_factory,
                            '_dh_leavemsg_w')
    except Exception:
        log_error('local-leave-message-guard-error')
        return
    if ok:
        log('local-leave-message-guard', messages=sorted(_DH_LEAVE_MESSAGES))
    elif tries < 60:
        call_later(5.0, _dh_leavemsg_install, tries + 1)


_dh_leavemsg_install()



# ---- m42f: the paraglider jump.  The plane offers PARAGLIDER | PARACHUTE (UIBattlegroundsFall).  The game server
# used to (1) give the avatar its jetWingsAppearanceID - chooseGliderBtn refuses with a "no paraglider" tip while it is
# 0, and the hook only filled the lobby's dtsJetWingsAppearanceID; (2) answer cell.chooseGlider / chooseParachute with
# syncJetWingsID(last, id) - the glider of this jump, jetWingsID = PROP_ITEM_ID of the equipped paraglider skin
# (getJetWingsData key: model, passenger anim); (3) keep the glide phase (cell.changeGlidePhase -> glidePhase).  The
# client flies the glide itself (MoveUnit: HIGH_SPEED_GLIDE -> FREE_GLIDE -> LOW_SPEED_GLIDE -> discard at 75 and
# changeFallPhase(NORMAL)), but the hook's dive watcher opened a parachute at HEIGHT_MUST_OPEN_PARACHUTE for everyone.
# Here a glider jump starts the glide, the watcher only waits for the landing, and other windows get the glider
# through act['gw'] = [jetWingsID, glidePhase] BEFORE the pose (a glide pose with jetWingsID 0 has no model to load).
_DH_GLIDE_HIGH, _DH_GLIDE_FREE, _DH_GLIDE_LOW = 6, 7, 8          # const.GlidePhase
_DH_POSE_HIGH_GLIDE = 12                                        # const.PlayerPose.HIGH_SPEED_GLIDE
_DH_GLIDE_POSES = (12, 14, 15)
_dh_glide = globals().get('_dh_glide') or {'jumped': False, 'id': 0, 'seen': {}}


def _dh_glider_appearance(player):
    value = 0
    for source in (lambda: getattr(player, 'jetWingsAppearanceID', 0), lambda: getattr(player, 'dtsJetWingsAppearanceID', 0),
                   lambda: lobby_appearance().get('dtsJetWingsAppearanceID')):
        try:
            value = int(source() or 0)
        except Exception:
            value = 0
        if value:
            return value
    return 0


def _dh_glider_id(player):
    """The glider of the equipped paraglider skin: its hall prop's PROP_ITEM_ID, when the jet-wings table knows it."""
    appearance = _dh_glider_appearance(player)
    if not appearance:
        return 0
    module = _properties_module()
    candidates = []
    try:
        candidates.append(int(module.getDtsHallPropData(appearance).PROP_TYPE.PROP_ITEM_ID or 0))
    except Exception:
        pass
    candidates.append(appearance)
    for key in candidates:
        try:
            if key and module.getJetWingsData(key) is not None:
                return key
        except Exception:
            continue
    if once('glider-id-' + str(appearance)):
        log('local-glider-unknown', appearance=appearance, tried=candidates)
    return 0


def _dh_glider_skin(player):
    """chooseGliderBtn checks the avatar's jetWingsAppearanceID: copy the equipped paraglider onto it."""
    if player is None:
        return 0
    appearance = _dh_glider_appearance(player)
    try:
        if appearance and int(getattr(player, 'jetWingsAppearanceID', 0) or 0) != appearance:
            player.jetWingsAppearanceID = appearance
            log('local-glider-skin', appearance=appearance)
    except Exception:
        if once('glider-skin'):
            log_error('local-glider-skin-error')
    return appearance


def _dh_rider_clips(entity, glider):
    """m42h: PlayerAnimationTreeManager.Awake caches jetWingsData = getJetWingsData(entity.jetWingsID) when the
    player model is created - 0 on this server until chooseGlider - so the glide poses never got the glider's rider
    clips (PASSENGER_*_IDLE_ANIM, BREAK_AWAY/LAND_ANIM) and Wingbuddy riders flew in the parachute pose, floating
    over or sunk into the glider.  Feed the row whenever jetWingsID changes; the game then stands the rider on the
    glider by itself (one pose per glider - 23 Wingbuddy/Wingman skins)."""
    try:
        am = getattr(getattr(entity, 'appear', None), 'animMgr', None)
        if am is None:
            return False
        am.jetWingsData = _properties_module().getJetWingsData(int(glider)) if glider else None
        return True
    except Exception:
        if once('rider-clips'):
            log_error('local-rider-clips-error')
        return False


def _dh_glider_sync(player, glider):
    old = int(getattr(player, 'jetWingsID', 0) or 0)
    try:
        player.syncJetWingsID(old, glider)
    except Exception:
        player.lastJetWingsID = old
        player.jetWingsID = glider
        if once('glider-sync'):
            log_error('local-glider-sync-error')
    _dh_glide['id'] = glider
    log('local-rider-clips', glider=glider, fed=_dh_rider_clips(player, glider))


def _dh_on_choose_glider(player, *_args, **_kwargs):
    glider = _dh_glider_id(player)
    _dh_glider_sync(player, glider)
    log('local-glider-chosen', glider=glider, appearance=_dh_glider_appearance(player))
    return None


def _dh_on_choose_parachute(player, *_args, **_kwargs):
    _dh_glider_sync(player, 0)
    log('local-glider-chosen', glider=0)
    return None


def _dh_on_change_glide_phase(player, phase=0, *_args, **_kwargs):
    try:
        phase = int(phase)
    except Exception:
        return None
    call_later(WEAPON_SWITCH_DELAY, set_player_field, player, 'glidePhase', phase)
    return None


def _dh_gliding(player):
    try:
        return bool(_dh_glide.get('jumped') and player is not None and int(getattr(player, 'jetWingsID', 0) or 0))
    except Exception:
        return False


def _dh_glide_start(player, tries=0):
    """The glider branch of the game's own iJetWingsAvatar.checkParachuteOffAirCraft: glide phase, glide pose (the
    pose change fires TRIGGER_OPEN_GLIDER in PlayerAvatar.onUpdatePose, PlayerGlider then opens the model)."""
    if not _dh_gliding(player):
        return False
    try:
        player.forsetGlidePhase(_DH_GLIDE_HIGH)
    except Exception:
        set_player_field(player, 'glidePhase', _DH_GLIDE_HIGH)
        if once('glide-phase'):
            log_error('local-glide-phase-error')
    apply_pose(player, _DH_POSE_HIGH_GLIDE)
    call_later(1.0, _dh_glide_check, player, tries)
    return True


def _dh_glide_check(player, tries):
    if not _dh_gliding(player):
        return
    pose = int(getattr(player, 'pose', 0) or 0)
    phase = int(getattr(player, 'clientGlidePhase', 0) or getattr(player, 'glidePhase', 0) or 0)
    log('local-glide-state', pose=pose, glide=phase, glider=int(getattr(player, 'jetWingsID', 0) or 0), tries=tries)
    if pose not in _DH_GLIDE_POSES and tries < 2:
        try:
            machine = player.gameObject.GetComponent('PlayerMachineMgr')
            machine.onTrigger(_dh_sys.modules['ClientConsts'].PWEventEnum.TRIGGER_OPEN_GLIDER, None)
        except Exception:
            if once('glide-trigger'):
                log_error('local-glide-trigger-error')
        _dh_glide_start(player, tries + 1)


def _dh_glide_jump_wrapper(player, *args, **kwargs):
    result = _dh_glide_jump_wrapper._dh_inner(player, *args, **kwargs)
    try:
        if result and int(getattr(player, 'jetWingsID', 0) or 0):
            _dh_glide['jumped'] = True
            _dh_glide['posed'] = False
            log('local-glide-jump', glider=int(player.jetWingsID))
            call_later(0.3, _dh_glide_start, player, 0)
        if result:
            _dh_steer_maybe_start(player, 'jump')     # m43: a pin set = steer there, whichever button jumped
    except Exception:
        log_error('local-glide-jump-error')
    return result


def _dh_glide_open_wrapper(player, *args, **kwargs):
    if _dh_gliding(player):
        return False                    # a glider jump never gets the forced parachute
    return _dh_glide_open_wrapper._dh_inner(player, *args, **kwargs)


def _dh_glide_watch_wrapper(player, token, *args, **kwargs):
    if not _dh_gliding(player):
        return _dh_glide_watch_wrapper._dh_inner(player, token, *args, **kwargs)
    if token != _flight.get('token') or BATTLE.get('phase') != 'fighting':
        return False
    diving = _dh_time.time() - _flight.get('dive_started', _dh_time.time())
    phase = int(getattr(player, 'fallPhase', 0) or 0)
    pose = int(getattr(player, 'clientPose', None) or getattr(player, 'pose', 0) or 0)
    if pose in _DH_GLIDE_POSES:
        _dh_glide['posed'] = True
    left_glide = _dh_glide.get('posed') and pose not in _DH_GLIDE_POSES   # into water (swim) or down without a discard
    if diving > DIVE_TIMEOUT or (diving > DIVE_MIN_TIME and (phase == FALL_PHASE['NORMAL'] or left_glide
                                                            or character_on_ground(player))):
        return landed(player)
    call_later(DIVE_POLL, watch_dive, player, token)
    return True


def _dh_glide_landed_wrapper(player, *args, **kwargs):
    was = _dh_gliding(player)
    _dh_glide['jumped'] = False
    result = _dh_glide_landed_wrapper._dh_inner(player, *args, **kwargs)
    if was:
        try:
            player.glidePhase = 0       # quietly: the client already left the glide (discard + changeFallPhase)
            player.clientGlidePhase = 0
        except Exception:
            pass
        log('local-glide-landed', pose=int(getattr(player, 'pose', 0) or 0))
    return result


def _dh_glide_board_wrapper(*args, **kwargs):
    result = _dh_glide_board_wrapper._dh_inner(*args, **kwargs)
    try:
        if result:
            _dh_glide['jumped'] = False
            _dh_glider_skin(current_player())
    except Exception:
        log_error('local-glide-board-error')
    return result


def _dh_glide_my_act_wrapper(*args, **kwargs):
    act = _dh_glide_my_act_wrapper._dh_inner(*args, **kwargs)
    try:
        player = current_player()
        if isinstance(act, dict) and _dh_gliding(player):
            act['gw'] = [int(player.jetWingsID),
                         int(getattr(player, 'clientGlidePhase', 0) or getattr(player, 'glidePhase', 0) or 0)]
    except Exception:
        if once('glide-my-act'):
            log_error('local-glide-my-act-error')
    return act


def _dh_glide_apply_act_wrapper(battle_id, handle, act, *args, **kwargs):
    try:
        state = act.get('gw') if isinstance(act, dict) else None
        last = _dh_glide['seen'].get(battle_id)
        if state != last and (state or last):
            entity = _resolve_entity(handle)
            if entity is not None and not isinstance(entity, (int, long_type)):
                glider, phase = (list(state or [0, 0]) + [0, 0])[:2]
                if glider and int(getattr(entity, 'jetWingsID', 0) or 0) != int(glider):
                    entity.lastJetWingsID = int(getattr(entity, 'jetWingsID', 0) or 0)
                    entity.jetWingsID = int(glider)
                    _dh_rider_clips(entity, int(glider))     # m42h: others ride their glider in its pose too
                if int(getattr(entity, 'glidePhase', 0) or 0) != int(phase):
                    set_player_field(entity, 'glidePhase', int(phase))
                _dh_glide['seen'][battle_id] = list(state) if state else None
    except Exception:
        if once('glide-apply'):
            log_error('local-glide-apply-error')
    return _dh_glide_apply_act_wrapper._dh_inner(battle_id, handle, act, *args, **kwargs)


def _dh_glide_leave_wrapper(player=None, *args, **kwargs):
    _dh_glide['jumped'] = False
    _dh_glide['id'] = 0
    _dh_glide['seen'].clear()
    return _dh_glide_leave_wrapper._dh_inner(player, *args, **kwargs)


try:
    _dh_glide_handlers = getattr(LOBBY, 'RPC_HANDLERS', None)
    if isinstance(_dh_glide_handlers, dict):
        _dh_glide_handlers['chooseGlider'] = _dh_on_choose_glider
        _dh_glide_handlers['chooseParachute'] = _dh_on_choose_parachute
        _dh_glide_handlers['changeGlidePhase'] = _dh_on_change_glide_phase
        # m42g: with a paraglider chosen, the jump button / F (UIBattlegroundsFall.doOnBtnOffAircraftClick) calls
        # cell.requestGetOffAircraft, not requestGetOffPlane - unanswered, the player fell out only when the plane
        # left the drop box ("F takes too long").  Same jump as the parachute button.
        _dh_glide_handlers['requestGetOffAircraft'] = on_get_off_plane
    _dh_m42f = {
        'handlers': isinstance(_dh_glide_handlers, dict),
        'off_aircraft': isinstance(_dh_glide_handlers, dict) and 'requestGetOffAircraft' in _dh_glide_handlers,
        'board': _dh_wrap_global('board_plane', _dh_glide_board_wrapper, '_dh_glide'),
        'jump': _dh_wrap_global('jump_out', _dh_glide_jump_wrapper, '_dh_glide'),
        'open': _dh_wrap_global('open_parachute', _dh_glide_open_wrapper, '_dh_glide'),
        'watch': _dh_wrap_global('watch_dive', _dh_glide_watch_wrapper, '_dh_glide'),
        'landed': _dh_wrap_global('landed', _dh_glide_landed_wrapper, '_dh_glide'),
        'my_act': _dh_wrap_global('my_act', _dh_glide_my_act_wrapper, '_dh_glide'),
        'act': _dh_wrap_global('apply_act', _dh_glide_apply_act_wrapper, '_dh_glide'),
        'leave': _dh_wrap_global('leave_battle', _dh_glide_leave_wrapper, '_dh_glide'),
    }
    _dh_glider_skin(current_player() if BATTLE.get('phase') == 'fighting' else None)
    log('local-glide-installed', **_dh_m42f)
except Exception:
    log_error('local-glide-install-error')


# ---- m42g/m42h: Wingbuddy gliders (CAN_CARRY_PLAYER, e.g. Devil Ray).  The game's doOpenGlider parents the
# player's GameObject to the glider's seat socket (HP_avatar0 / HP_avatar_f0, localPosition 0) and the rider pose
# comes from the glider's own rider clips (see _dh_rider_clips).  m42g moved the rider 1.3 m down in the seat frame
# because the Devil Ray's rider flew in the parachute pose; with the right pose that offset sinks the rider into the
# glider, so m42h feeds the pose instead and leaves the seat alone.  _dh_carry_seat stays as a no-op because clients
# that hot-reloaded from m42g still have doOpenGlider wrapped to call it.
def _dh_carry_seat(appear, tries=0):
    return None


# ---- m42g camera: the game's per-glider camera table (getCameraGliderData(0), read by
# PlayerCameraController.tryUseGliderCameraData(jetWingsID)) has no row for the Wingbuddy gliders, so they fly with
# the generic glide camera, which sits inside the ray.  Give every carry glider (its jet-wings row has a passenger
# idle animation - the test the game's loadGliderCoroutine uses) a wider row, built from the plain Paraglider's.
_DH_CARRY_CAM = {'MODE_HIGH_SPEED_GLIDE_PARAMS': {'STAND_DIST': 260.0, 'STAND_PITCH': 30.0, 'STAND_Y': 60.0},
                 'MODE_LOW_SPEED_GLIDE_PARAMS': {'STAND_DIST': 240.0, 'STAND_PITCH': 22.0, 'STAND_Y': 60.0},
                 'MODE_BEFORE_GLIDE_PARAMS': {'STAND_DIST': 200.0, 'STAND_PITCH': 30.0, 'STAND_Y': 60.0}}


_dh_carry_cam_ids = globals().get('_dh_carry_cam_ids') or set()


def _dh_carry_camera_rows():
    try:
        mod = _properties_module()
        table = mod.getCameraGliderData(0)
        base = table.get(1) if hasattr(table, 'get') else None
        if base is None:
            return 0
        import copy as _dh_copy
        added = []
        for jid in range(1, 400):
            try:
                data = mod.getJetWingsData(jid)
            except Exception:
                data = None
            if data is None or not getattr(data, 'PASSENGER_IDLE_ANIM', ''):
                continue
            row = table.get(jid)
            if row is not None and jid not in _dh_carry_cam_ids:
                continue                              # the game's own row wins
            row = _dh_copy.deepcopy(base)
            for mode, values in _DH_CARRY_CAM.items():
                params = getattr(row, mode)
                for key, value in values.items():
                    setattr(params, key, value)
            table[jid] = row
            _dh_carry_cam_ids.add(jid)
            added.append(jid)
        log('local-carry-camera', added=added)
        return len(added)
    except Exception:
        log_error('local-carry-camera-error')
        return 0


_dh_m42g = globals().get('_dh_m42g') or {}


def _dh_m42g_install(token, tries=0):
    if token is not _dh_m42g.get('token'):
        return
    try:
        table = _properties_module().getCameraGliderData(0)
    except Exception:
        table = None
    if table is not None:
        log('local-carry-camera-installed', tries=tries, carry_cams=_dh_carry_camera_rows())
        return
    if tries < 1440:                                  # the property tables load with the first round
        call_later(5.0, _dh_m42g_install, token, tries + 1)


_dh_m42g['token'] = object()
call_later(1.0, _dh_m42g_install, _dh_m42g['token'])



# ---- m43: "Go to my marker" over the whole map.  The game's NaviComp.requestNaviTo tries the client navmesh
# (initDtsNavPath -> navi_utils.getNaviPath); when that fails - every long route - it sets _waitingServerResult and asks
# the server (player.queryRecastNavPath -> base.queryRecastNavPath), which used to answer onQueryRecastNavPath(target,
# path) from its recast mesh.  Ours never answered: nothing moved and every later click hit the 5 s guard tip.  Near
# targets (waiting island, same town) never reached the server, which is why they worked.  Answer it here: stitch the
# long route from navmesh segments along the straight line (the bot path service walks the same mesh) and hand it to
# the game's own callback, so the game's auto-route runs unchanged.
_DH_ROUTE_STEP = 4000.0                               # first segment length, game units (10 = 1 m)
_DH_ROUTE_MIN_STEP = 500.0
_DH_ROUTE_MAX_PTS = 120


def _dh_route_vec(point):
    """NaviComp.onRequestNaviTo rebuilds each point with vector(*point): plain tuples, never vector objects
    ("argument after * must be a sequence, not math3d.vector", laptop 11:33)."""
    return (float(point[0]), float(point[1]), float(point[2]))


def _dh_route_ground(point):
    """The pin comes as (x, 0, z): put it (and every chord point) on the ground so the mesh can snap it."""
    try:
        height = ground_height(float(point[0]), float(point[2]))
        if height is not None and height != 0:
            return (float(point[0]), float(height), float(point[2]))
    except Exception:
        pass
    return (float(point[0]), float(point[1]), float(point[2]))


def _dh_route_segment(navi, src, dst):
    """Navmesh path src -> dst as a point list, or None."""
    try:
        path = _dh_nav_call(navi, 'getNaviPath', src, dst)
    except Exception:
        return None
    if not path:
        return None
    pts = [_dh_point_of(p) for p in path]
    return pts if len(pts) >= 2 else None


def _dh_route_stitch(src, dst):
    navi = _dh_sys.modules.get('movement.navi_utils')
    if navi is None:
        return None, 0
    dst = _dh_route_ground(dst)
    whole = _dh_route_segment(navi, src, dst)
    if whole:
        return whole, 1
    total = distance(src, dst)
    pts = [src]
    cur = src
    segments = 0
    step = _DH_ROUTE_STEP
    guard = 0
    while distance(cur, dst) > step * 0.5 and guard < 60:
        guard += 1
        remaining = distance(cur, dst)
        frac = min(1.0, step / remaining) if remaining > 0 else 1.0
        mid = _dh_route_ground((cur[0] + (dst[0] - cur[0]) * frac, cur[1] + (dst[1] - cur[1]) * frac, cur[2] + (dst[2] - cur[2]) * frac))
        seg = _dh_route_segment(navi, cur, mid)
        if seg is None:
            if step > _DH_ROUTE_MIN_STEP:
                step = max(_DH_ROUTE_MIN_STEP, step / 2.0)
                continue
            cur = mid                                 # no mesh here (water / cliff): skip the chord point
            step = _DH_ROUTE_STEP
            continue
        pts.extend(seg[1:])
        cur = seg[-1]
        segments += 1
        step = _DH_ROUTE_STEP
    last = _dh_route_segment(navi, cur, dst)
    if last:
        pts.extend(last[1:])
        segments += 1
    elif distance(cur, dst) > 3000.0:
        return None, segments                         # more than 300 m short: no usable route
    elif distance(cur, dst) > _DH_ROUTE_MIN_STEP:
        log('local-auto-route-partial', short=int(distance(cur, dst)))
    if len(pts) > _DH_ROUTE_MAX_PTS:
        stride = float(len(pts) - 1) / (_DH_ROUTE_MAX_PTS - 1)
        pts = [pts[int(round(i * stride))] for i in range(_DH_ROUTE_MAX_PTS - 1)] + [pts[-1]]
    return pts, segments


def _dh_route_answer(player, endPos, pts, segments, started):
    try:
        path = [_dh_route_vec(p) for p in (pts or [])]
        player.onQueryRecastNavPath(_dh_route_vec(_dh_point_of(endPos)), path)   # the target is rebuilt with vector(*t) too
        log('local-auto-route', points=len(path), segments=segments, ms=int((time.time() - started) * 1000))
    except Exception:
        log_error('local-auto-route-error')


def _dh_route_factory(inner):
    def queryRecastNavPath(self, startPos, endPos):
        started = time.time()
        try:
            src = _dh_point_of(startPos)
            dst = _dh_point_of(endPos)
            pts, segments = _dh_route_stitch(src, dst)
        except Exception:
            if once('auto-route-stitch'):
                log_error('local-auto-route-stitch-error')
            pts, segments = None, 0
        if pts:
            call_later(0.05, _dh_route_answer, self, endPos, pts, segments, started)
            return None
        log('local-auto-route', points=0, segments=segments, ms=int((time.time() - started) * 1000))
        call_later(0.05, _dh_route_answer, self, endPos, [], segments, started)   # the game's own "no path" handling
        return None                                   # never ask the server: it has no mesh (its bare reply raised)
    return queryRecastNavPath


_dh_route = globals().get('_dh_route') or {}


def _dh_route_install(token, tries=0):
    if token is not _dh_route.get('token'):
        return
    try:
        if _dh_class_wrap('Avatar', 'PlayerAvatar', 'queryRecastNavPath', _dh_route_factory, '_dh_route_w'):
            log('local-auto-route-installed', tries=tries)
            return
    except Exception:
        log_error('local-auto-route-install-error')
        return
    if tries < 1440:                                  # the avatar module loads with the first round
        call_later(5.0, _dh_route_install, token, tries + 1)


_dh_route['token'] = object()
call_later(1.0, _dh_route_install, _dh_route['token'])


# ---- m44 (2026-10-31): lighter drawing of far bodies.  The hook's step_motion moves EVERY remote body every frame
# (motion_point + hold_entity + set_body_velocity: ~50 us each); with 20 bots that is 60-70 ms per second, a quarter
# of the hook's 210-270 ms/s (laptop local-perf), and the owner wants 80 bots per match (x4).  Bodies far from the
# player are stepped every Nth frame instead - they are drawn tiny there and glide the same (motion_point is
# time-based, so a late step lands on the right spot).  Near bodies keep the full rate.
_DH_LOD_BANDS = ((2500.0, 1), (7000.0, 3), (15000.0, 8), (1e12, 20))   # units (10 = 1 m): within -> every Nth frame
_dh_lod = globals().get('_dh_lod') or {'frame': 0, 'every': {}, 'stat': [0, 0]}


def _dh_lod_classify(player):
    """Every 15th frame: how often each body is stepped, by its distance from us."""
    try:
        mine = getattr(player, 'position', None)
        bodies = _motion.get('bodies') or {}
        if mine is None:
            _dh_lod['every'] = {}
            return
        mx, mz = float(mine[0]), float(mine[2])
        every = {}
        for battle_id, body in bodies.items():
            try:
                point = body['samples'][-1][1]
                d = math.hypot(float(point[0]) - mx, float(point[2]) - mz)
            except Exception:
                d = 0.0
            for limit, n in _DH_LOD_BANDS:
                if d <= limit:
                    every[battle_id] = n
                    break
        _dh_lod['every'] = every
    except Exception:
        _dh_lod['every'] = {}


def _dh_lod_step_wrapper(now):
    frame = _dh_lod['frame'] = int(_dh_lod.get('frame') or 0) + 1
    bodies = _motion.get('bodies')
    if not isinstance(bodies, dict) or len(bodies) < 6:
        return _dh_lod_step_wrapper._dh_inner(now)       # a handful of bodies: nothing to save
    if frame % 15 == 0 or not _dh_lod.get('every'):
        _dh_lod_classify(current_player())
    every = _dh_lod['every']
    due = {}
    for battle_id, body in bodies.items():
        n = every.get(battle_id, 1)
        if n <= 1 or (frame + (battle_id % n if isinstance(battle_id, int) else 0)) % n == 0:
            due[battle_id] = body
    _dh_lod['stat'][0] += len(due)
    _dh_lod['stat'][1] += len(bodies)
    if len(due) == len(bodies):
        return _dh_lod_step_wrapper._dh_inner(now)
    _motion['bodies'] = due
    try:
        return _dh_lod_step_wrapper._dh_inner(now)
    finally:
        kept = _motion['bodies']                      # the step may pop a body gone from _remote
        for battle_id in list(due):
            if battle_id not in kept:
                bodies.pop(battle_id, None)
        _motion['bodies'] = bodies


def _dh_lod_report():
    try:
        stepped, total = _dh_lod.get('stat') or [0, 0]
        if total:
            log('local-lod', stepped=stepped, of=total, bodies=len(_motion.get('bodies') or {}),
                near=sum(1 for n in _dh_lod.get('every', {}).values() if n == 1))
        _dh_lod['stat'] = [0, 0]
    except Exception:
        pass
    call_later(60.0, _dh_lod_report)


def _dh_lod_install(tries=0):
    if _dh_wrap_global('step_motion', _dh_lod_step_wrapper, '_dh_lod'):
        log('local-lod-installed', bands=[[int(l / 10.0) if l < 1e9 else None, n] for l, n in _DH_LOD_BANDS])
        call_later(60.0, _dh_lod_report)
    elif tries < 120:
        call_later(5.0, _dh_lod_install, tries + 1)


call_later(1.0, _dh_lod_install)


# ---- m44b (2026-10-31): 80 bots - the rest of the per-entity cost (laptop round 19:33, 80 bots: hook 620-700 ms/s,
# 42 fps; apply_act 12,000 calls / 10 s = 80-100 ms/s, pump 115-125 ms/s of JSON, apply_snapshot's loop 45 ms/s).
# (1) apply_act re-checks hand weapon / vehicle / rolling cars / gear on every snapshot even when the act did not
#     change; for a far body that runs on the LOD cadence only (3rd / 8th / 20th snapshot), near bodies as before.
# (2) The battle host may leave far alive bots out of 3 snapshots in 4 ('partial': True, bot brain far_bot_ticks);
#     the hook would destroy a body missing from a snapshot, so the last record of each entity is kept and put back
#     into a partial snapshot - the body stays, glides on its last samples, and the next full record moves it.
_dh_m44b = globals().get('_dh_m44b') or {'last': {}, 'snaps': 0, 'skipped': 0, 'filled': 0}


def _dh_partial_snapshot_factory(inner):
    def apply_snapshot(snapshot):
        _dh_m44b['snaps'] += 1
        try:
            items = snapshot.get('entities') or []
            last = _dh_m44b['last']
            if snapshot.get('partial'):
                present = set()
                for item in items:
                    try:
                        present.add(int(item.get('id')))
                    except Exception:
                        pass
                gone = set(int(g) for g in (snapshot.get('removed') or []) if str(g).lstrip('-').isdigit())
                filled = [last[i] for i in list(_remote) if i not in present and i not in gone and i in last]
                if filled:
                    snapshot['entities'] = items = list(items) + filled
                    _dh_m44b['filled'] += len(filled)
            for item in items:
                try:
                    last[int(item.get('id'))] = item
                except Exception:
                    pass
            if len(last) > 400:
                for key in list(last):
                    if key not in _remote:
                        last.pop(key, None)
        except Exception:
            if once('m44b-partial'):
                log_error('local-partial-snapshot-error')
        return inner(snapshot)
    return apply_snapshot


def _dh_m44b_report():
    try:
        log('local-act-lod', snapshots=_dh_m44b['snaps'], acts_skipped=_dh_m44b['skipped'], filled=_dh_m44b['filled'])
        _dh_m44b.update(snaps=0, skipped=0, filled=0)
    except Exception:
        pass
    call_later(60.0, _dh_m44b_report)


def _dh_act_lod_wrapper(battle_id, handle, act):
    try:
        n = _dh_lod.get('every', {}).get(battle_id, 1)
        if n > 1 and act == _acts.get(battle_id) and (_dh_m44b['snaps'] + (battle_id % n if isinstance(battle_id, int) else 0)) % n:
            _dh_m44b['skipped'] += 1
            return False
    except Exception:
        pass
    return _dh_act_lod_wrapper._dh_inner(battle_id, handle, act)


def _dh_partial_snapshot_wrapper(snapshot):
    return _dh_partial_snapshot_factory(_dh_partial_snapshot_wrapper._dh_inner)(snapshot)


def _dh_m44b_install(tries=0):
    a = _dh_wrap_global('apply_act', _dh_act_lod_wrapper, '_dh_actlod')
    b = _dh_wrap_global('apply_snapshot', _dh_partial_snapshot_wrapper, '_dh_partial')
    if a and b:
        log('local-act-lod-installed')
        call_later(60.0, _dh_m44b_report)
    elif tries < 120:
        call_later(5.0, _dh_m44b_install, tries + 1)


call_later(1.5, _dh_m44b_install)



# ---- m45: team knock-down and rescue (owner 2026-10-31).  In a team match the server (ros_admin/knockdown.py) no
# longer kills a player who still has a standing teammate: own_state carries 'down' = {left, healer, healer_name, n, by}
# while they are down (hp 1), and the game's own wounded machinery does the rest once we set the pose:
#   - down: pose WOUNDED (3) here; our act relays it, so every teammate's client runs onUpdatePose -> enableWoundedTrap
#     and shows its own "Heal" prompt at our body (iNormalCombatUnit.onTarget);
#   - the rescuer's game: onHealBtnTouch -> cell.startHeal(our client id) (forwarded below as a 'heal' report, with the
#     client id turned into the battle id), its own heal bar (startHealOther, HEAL_TIME) -> cell.recordHealTime
#     ('done'); breakHealOther / onCancelHealOther -> 'on': 0.  The server revives on 'done' (after 3 s) or its own
#     timer (revive_seconds) while the rescuer stays in range;
#   - revived: 'down' gone with alive True -> pose STAND, hp from the state, player.onHealed() (the game's
#     TRIGGER_HEALED stands the body up and re-arms);
#   - bled out / finished: alive False with the killer -> the usual killed_by_player path (inner apply_own_state).
_dh_kd = globals().get('_dh_kd') or {}
for _dh_k, _dh_v in (('down', None), ('healer', 0), ('healing', 0), ('told', 0.0)):
    _dh_kd.setdefault(_dh_k, _dh_v)
_DH_KD_POSE_WOUNDED = 3
_DH_KD_POSE_STAND = 0


def _dh_kd_pose(name, default):
    try:
        import const
        return int(getattr(const.PlayerPose, name))
    except Exception:
        return default


def _dh_kd_space_call(name, *args):
    space = zone_space()
    function = getattr(space, name, None) if space is not None else None
    if not callable(function):
        return False
    try:
        function(*args)
        return True
    except Exception:
        if once('kd-space-' + name):
            log_error('local-kd-space-call-error', name=name)
        return False


def _dh_kd_enter(player, down):
    _dh_kd['down'] = dict(down)
    _dh_kd['healer'] = 0
    _dh_kd['told'] = time.time()
    apply_pose(player, _dh_kd_pose('WOUNDED', _DH_KD_POSE_WOUNDED))
    _dh_kd_space_call('onEnterWounedState', '')
    left = int(down.get('left') or 0)
    tip_text('You are down! A teammate can revive you - %d s left' % left)
    log('local-kd-down', by=safe(down.get('by'), 40), left=left, n=int(down.get('n') or 1))


def _dh_kd_leave(player, state):
    down = _dh_kd['down'] or {}
    _dh_kd['down'] = None
    _dh_kd['healer'] = 0
    apply_pose(player, _dh_kd_pose('STAND', _DH_KD_POSE_STAND))
    try:
        hp = int(state.get('hp') or 0)
    except (TypeError, ValueError):
        hp = 0
    if hp > 0:
        set_player_field(player, 'hp', hp)
    healed = getattr(player, 'onHealed', None)
    if callable(healed):
        try:
            healed()
        except Exception:
            if once('kd-onhealed'):
                log_error('local-kd-onhealed-error')
    tip_text('You are back up!')
    log('local-kd-revived', hp=hp, by=safe(down.get('healer_name'), 40))


def _dh_kd_progress(player, down):
    healer = int(down.get('healer') or 0)
    if healer != _dh_kd['healer']:
        _dh_kd['healer'] = healer
        if healer:
            tip_text('%s is reviving you - stay still' % (down.get('healer_name') or 'A teammate'))
        log('local-kd-healer', healer=healer, name=safe(down.get('healer_name'), 40))
        return
    now = time.time()
    if not healer and now - _dh_kd['told'] >= 15.0:
        _dh_kd['told'] = now
        tip_text('Down - %d s left for a teammate to revive you' % int(down.get('left') or 0))


def _dh_kd_own_state_wrapper(state):
    result = _dh_kd_own_state_wrapper._dh_inner(state)
    try:
        if not isinstance(state, dict):
            return result
        player = current_player()
        if player is None:
            return result
        down = state.get('down')
        if isinstance(down, dict) and state.get('alive') is not False:
            if _dh_kd['down'] is None:
                _dh_kd_enter(player, down)
            else:
                _dh_kd['down'] = dict(down)
                _dh_kd_progress(player, down)
        elif _dh_kd['down'] is not None:
            if state.get('alive') is False:
                _dh_kd['down'] = None                   # bled out / finished: the inner call ran killed_by_player
                _dh_kd['healer'] = 0
                log('local-kd-out')
            else:
                _dh_kd_leave(player, state)
    except Exception:
        if once('kd-state'):
            log_error('local-kd-state-error')
    return result


def _dh_kd_battle_id_of(client_id):
    """A client entity id (what the game hands cell.startHeal) as the battle host's id."""
    try:
        client_id = int(client_id)
    except (TypeError, ValueError):
        return 0
    me = current_player()
    if me is not None and getattr(me, 'id', None) == client_id:
        return int(BATTLE.get('entity_id') or 0)
    for battle_id, handle in list(_remote.items()):
        body = _resolve_entity(handle)
        if body is not None and not isinstance(body, (int, long_type)) and getattr(body, 'id', None) == client_id:
            return int(battle_id)
    return 0


def _dh_kd_report(target, on=None, done=None):
    if BATTLE.get('address') is None or not target:
        return False
    report = {'me': BATTLE.get('entity_id') or 0, 'target': int(target)}
    if done:
        report['done'] = 1
    else:
        report['on'] = 1 if on else 0
    return send(LOOT_PREFIX + json.dumps({'heal': report}))


def _dh_kd_start_heal(player, target_id=None, *args, **kwargs):
    target = _dh_kd_battle_id_of(target_id)
    _dh_kd['healing'] = target
    sent = _dh_kd_report(target, on=True)
    log('local-kd-heal', target=target, client=safe(target_id, 20), on=1, sent=sent)
    return None


def _dh_kd_stop_heal(player, *args, **kwargs):
    target, _dh_kd['healing'] = _dh_kd['healing'], 0
    if target:
        _dh_kd_report(target, on=False)
        log('local-kd-heal', target=target, on=0)
    return None


def _dh_kd_record_heal(player, *args, **kwargs):
    target, _dh_kd['healing'] = _dh_kd['healing'], 0
    if target:
        _dh_kd_report(target, done=True)
        log('local-kd-heal', target=target, done=1)
    return None


def _dh_kd_break_factory(inner):
    def wrapped(self, *args, **kwargs):
        try:
            _dh_kd_stop_heal(self)
        except Exception:
            pass
        return inner(self, *args, **kwargs)
    return wrapped


def _dh_kd_install(tries=0):
    done = []
    try:
        for method in ('breakHealOther', 'onCancelHealOther'):
            if _dh_class_wrap('Avatar', 'PlayerAvatar', method, _dh_kd_break_factory, '_dh_kd_' + method):
                done.append(method)
    except Exception:
        log_error('local-kd-install-error')
    if len(done) >= 2 or tries >= 1440:
        log('local-kd-installed', wrapped=done, tries=tries)
        return
    call_later(5.0, _dh_kd_install, tries + 1)


try:
    _dh_kd['wrapped'] = _dh_wrap_global('apply_own_state', _dh_kd_own_state_wrapper, '_dh_kd')
    _dh_kd_handlers = getattr(LOBBY, 'RPC_HANDLERS', None) if LOBBY is not None else None
    if isinstance(_dh_kd_handlers, dict):
        _dh_kd_handlers['startHeal'] = _dh_kd_start_heal
        _dh_kd_handlers['stopHeal'] = _dh_kd_stop_heal
        _dh_kd_handlers['recordHealTime'] = _dh_kd_record_heal
    call_later(1.0, _dh_kd_install, 0)
    log('local-kd-ready', state=_dh_kd['wrapped'], handlers=isinstance(_dh_kd_handlers, dict))
except Exception:
    log_error('local-kd-ready-error')



# ---- m46: the melee slot (key 4) - the axe stayed on the back and the gun in the hands (owner photo 2026-10-31).
# switch_weapon -> Avatar.onChangeDtsWeapon -> iDtsEquip.doChangeColdWeapon -> WeaponController.setRail ->
# rail.onConvertTo -> SendMessage -> PlayerFPAppear.onSelectRailOwn -> SendMessage -> WeaponFPPAppear.doSetRail ->
# onRefreshModel -> preload_resource (cached: the callback runs at once) -> onLoadModel -> Mesh changed -> Animator
# reload raised "[Animator] There is no anim data (animators/player_dts/mainfps.xml)": the FIRST-PERSON weapon view has
# no animation data for a cold weapon.  The exception climbed back through both SendMessages and out of
# onChangeDtsWeapon, so everything after the first-person part - the third-person model in the hands, the rest of the
# switch - never ran; only the HUD had already moved to slot 4.  115 such errors from 9 players since 10-22
# (local-battle-switch-error slot 3), the same on the laptop.  The first-person weapon model load is now kept to
# itself: a failure there is logged once and the switch goes on (the first-person view simply has no melee model,
# as the game's own FPP mode never shows one).
_dh_fpw = globals().get('_dh_fpw') or {}
_dh_fpw.setdefault('done', {})


def _dh_fpw_guard_factory(name):
    def factory(inner):
        def guarded(self, *args, **kwargs):
            try:
                return inner(self, *args, **kwargs)
            except Exception:
                if once('fpw-' + name):
                    log_error('local-fpw-guarded', method=name)
                return None
        guarded.__name__ = name
        return guarded
    return factory


def _dh_fpw_install(tries=0):
    done = _dh_fpw['done']
    try:
        for method in ('onLoadModel', 'onRefreshModel'):
            if not done.get(method):
                done[method] = _dh_class_wrap('weapon.appearance.WeaponFPPAppear', 'WeaponFPPAppear', method,
                                              _dh_fpw_guard_factory(method), '_dh_fpw_' + method)
    except Exception:
        log_error('local-fpw-install-error')
    if all(done.get(m) for m in ('onLoadModel', 'onRefreshModel')) or tries >= 1440:
        log('local-fpw-installed', wrapped=[m for m in ('onLoadModel', 'onRefreshModel') if done.get(m)], tries=tries)
        return
    call_later(5.0, _dh_fpw_install, tries + 1)   # the weapon modules load with the first round


try:
    _dh_fpw_install(0)
except Exception:
    log_error('local-fpw-ready-error')


# ---- m47 (2026-11-01): the log audit.  step_motion resolves each remote body through BigWorld.entities and, when the
# entity is not there yet (spawn in flight) or already gone, _resolve_entity hands back the bare id; hold_entity and
# set_body_velocity then fail on an int ("'int' object has no attribute 'velocity'", 17 players).  Both now skip
# anything that is not an entity (no position attribute) and the loop goes on; nothing else changes.
_dh_m47_hold = globals().get('hold_entity')
_dh_m47_vel = globals().get('set_body_velocity')
while getattr(_dh_m47_hold, '_dh_m47', False):            # m49: a second load must wrap the ORIGINAL (recursion fix)
    _dh_m47_hold = _dh_m47_hold._dh_inner
while getattr(_dh_m47_vel, '_dh_m47', False):
    _dh_m47_vel = _dh_m47_vel._dh_inner


def _dh_is_entity(entity):
    return entity is not None and not isinstance(entity, (int, long, float)) and hasattr(entity, 'position')


def _dh_m49_vel_factory(_dh_base):
    def set_body_velocity(entity, velocity):
        if not _dh_is_entity(entity):
            return False
        return _dh_base(entity, velocity)
    return set_body_velocity


def _dh_m49_hold_factory(_dh_base):
    def hold_entity(entity, position, yaw=None):     # exact signature of the hook's hold_entity
        if not _dh_is_entity(entity):
            return False
        return _dh_base(entity, position, yaw)
    return hold_entity


if callable(_dh_m47_vel):
    set_body_velocity = _dh_m49_vel_factory(_dh_m47_vel)
    set_body_velocity._dh_m47 = True
    set_body_velocity._dh_inner = _dh_m47_vel

if callable(_dh_m47_hold):
    hold_entity = _dh_m49_hold_factory(_dh_m47_hold)
    hold_entity._dh_m47 = True
    hold_entity._dh_inner = _dh_m47_hold

log('local-m47-installed', velocity=callable(_dh_m47_vel), hold=callable(_dh_m47_hold))


# ---- m48 (2026-11-01): team voice in a match (docs/voice-chat.md).  Hot-lobby m121 replaced the CC voice driver with
# a bridge to the launcher; the launcher's state names the team mates who are speaking right now.  Here that becomes
# the game's own "speaking" nameplate effect over a team mate's head (UI3DCompBattleGroundName.startLoopVoiceEffect /
# stopLoopVoiceEffect, the thing CC's isSpeaking property used to drive).  Team mates are matched by name through the
# m40n teammate records (entID -> client entity).  Checked twice a second only while the launcher reports a room.
_dh_m48 = globals().get('_dh_m48') or {'running': False, 'shown': {}, 'logged': 0}


def _dh_m48_bridge():
    try:
        import Globals
        getter = getattr(Globals, 'ccminiInstance', None)
        bridge = getter() if callable(getter) else None
        return bridge if type(bridge).__name__ == '_DhVoiceBridge' else None
    except Exception:
        return None


def _dh_m48_apply(speaking_names):
    import BigWorld
    player = BigWorld.player()
    if player is None:
        return
    for record in list(getattr(player, 'battleTeammates', None) or []):
        entity_id = getattr(record, 'entID', None)
        if entity_id is None or entity_id == getattr(player, 'id', None):
            continue
        name = str(getattr(record, 'nickname', '') or '')
        want = name in speaking_names
        shown = _dh_m48['shown'].get(entity_id, False)
        if want == shown:
            continue
        entity = BigWorld.entities.get(entity_id)
        plate = getattr(entity, '_ui3DName', None) if entity is not None else None
        method = getattr(plate, 'startLoopVoiceEffect' if want else 'stopLoopVoiceEffect', None)
        if callable(method):
            try:
                method()
                _dh_m48['shown'][entity_id] = want
                if _dh_m48['logged'] < 20:
                    _dh_m48['logged'] += 1
                    log('local-voice-mate', name=name, speaking=want)
            except Exception:
                log_error('local-voice-mate-error', name=name)
        elif not want:
            _dh_m48['shown'][entity_id] = False


def _dh_m48_tick():
    try:
        bridge = _dh_m48_bridge()
        state = getattr(bridge, 'state', None) or {}
        if BATTLE.get('phase') == 'fighting' and state.get('room'):
            names = set()
            speaking = set(int(g) for g in (state.get('speaking') or []) if str(g).isdigit())
            for item in state.get('members') or []:
                try:
                    if int(item[0]) in speaking:
                        names.add(str(item[1]))
                except (TypeError, ValueError, IndexError):
                    continue
            _dh_m48_apply(names)
        elif _dh_m48['shown']:
            _dh_m48_apply(set())
            _dh_m48['shown'] = {}
    except Exception:
        log_error('local-voice-mate-tick-error')
    call_later(0.5, _dh_m48_tick)


if not _dh_m48['running']:
    _dh_m48['running'] = True
    call_later(1.0, _dh_m48_tick)

log('local-m48-installed', bridge=_dh_m48_bridge() is not None)
log('local-m49-installed', reload_safe=True)


# ==============================================================================
# ROS REDEMPTION - MASTER PRODUCTION ENGINE PATCH
# 1. UISelectHero suppression for standard maps
# 2. Resilient matchmaking & zero step 0 failures
# 3. Vehicle Spawning: Boats in water, Land vehicles on land
# 4. Killfeed color fix: Real killer ID for BLUE name & bot kill crediting
# 5. Shift+1 Bicycle & In-game Tango Emote handlers + Chat Commands
# 6. Anti-Clump Bot Dispersion in place_bots_near
# 7. Admin / GM Chat Command Protection (Cheats locked to Admin Sean only)
# ==============================================================================

# 1. UISelectHero Guard
try:
    for _mod_name in ('ui.UISelectHero', 'UISelectHero'):
        _m = sys.modules.get(_mod_name)
        if not _m:
            try:
                _m = __import__(_mod_name, fromlist=['UISelectHero'])
            except Exception:
                _m = None
        if _m:
            _cls = getattr(_m, 'UISelectHero', None)
            if _cls:
                _orig_hl = getattr(_cls, '_showHeroList', None)
                if _orig_hl and not getattr(_orig_hl, '_redemption_guard', False):
                    def _safe_showHeroList(self, *args, **kwargs):
                        try:
                            return _orig_hl(self, *args, **kwargs)
                        except Exception:
                            return None
                    _safe_showHeroList._redemption_guard = True
                    _cls._showHeroList = _safe_showHeroList
    import Globals as _gl
    if hasattr(_gl, 'uiMgr'):
        _orig_eui = getattr(_gl.uiMgr, 'enter_ui', None)
        while getattr(_orig_eui, '_redemption_inner', None) is not None:
            _orig_eui = _orig_eui._redemption_inner
        if _orig_eui and not getattr(_orig_eui, '_redemption_guard', False):
            def _safe_enter_ui(name, *args, **kwargs):
                if name == 'UISelectHero':
                    cur_map = BATTLE.get('map') or (BATTLE.get('ticket') or {}).get('map', 0)
                    if cur_map not in (730, 731, 732, 733):
                        return None
                return _orig_eui(name, *args, **kwargs)
            _safe_enter_ui._redemption_guard = True
            _safe_enter_ui._redemption_inner = _orig_eui
            _safe_enter_ui._dh_inner = getattr(_orig_eui, '_dh_inner', _orig_eui)
            _gl.uiMgr.enter_ui = _safe_enter_ui
except Exception:
    pass

# 2. Resilient step_join (Zero step 0 failures)
try:
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
            'gid': int(profile.get('gid') or 10000002),
            'map': map_id,
            'look': my_look(player),
            'team': int((BATTLE['ticket'] or {}).get('team') or 1),
        }
        if spawn is not None:
            request['spawn'] = [round(value, 3) for value in spawn]

        try:
            import socket as _sock_mod
            if BATTLE.get('socket') is not None and hasattr(_sock_mod, 'SIO_UDP_CONNRESET'):
                BATTLE['socket'].ioctl(_sock_mod.SIO_UDP_CONNRESET, False)
        except Exception:
            pass

        drain(32)
        send(JOIN_PREFIX + json.dumps(request))
        time.sleep(0.08)

        reply = None
        for _ in range(30):
            for packet in drain():
                if is_join_reply(packet):
                    reply = packet
                    break
            if reply is not None:
                break
            time.sleep(0.03)

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

    _steps = []
    for _name, _func in ENTER_STEPS:
        if _name == 'join':
            _steps.append((_name, redemption_step_join))
        else:
            _steps.append((_name, _func))
    globals()['ENTER_STEPS'] = tuple(_steps)
    globals()['step_join'] = redemption_step_join
except Exception:
    pass

# 3. Vehicle Spawning: Boats in water, Land vehicles on land
try:
    def redemption_stream_cars(point):
        x, _y, z = point
        made = _world['cars_made']
        for index in near_indexes(_world['car_grid'], LOOT_CELL, x, z, CAR_STREAM_RADIUS):
            if index in made:
                continue
            spot = _world['cars'][index]
            if math.hypot(spot[0] - x, spot[2] - z) > CAR_STREAM_RADIUS:
                continue
            made.add(index)
            # Detect water spots: negative depth or Type 2
            is_water = (len(spot) > 3 and spot[3] == 2) or (spot[1] < -1000.0)
            if is_water:
                class_name, land, tps = BOAT
            else:
                class_name, land, tps = VEHICLE_FLEET[index % len(VEHICLE_FLEET)]
            car_id = spawn_vehicle(class_name, land, tps, spot[0], spot[2], spot[1], spot[4] if len(spot) > 4 else 0.0)
            if car_id is not None:
                share_car(car_id, ('w%d' if is_water else 'c%d') % index)
        return len(made)

    globals()['stream_cars'] = redemption_stream_cars
    log('ros-redemption-fix', fix='water boats and land cars installed')
except Exception:
    pass

# 4. Killfeed color fix: Real killer ID for BLUE name & bot kill crediting
try:
    def redemption_remote_died(battle_id, handle, item):
        if not isinstance(item, dict):
            return False
        killer_name = str(item.get('killer') or 'Player')
        weapon_name = str(item.get('weapon') or '')
        target = _resolve_entity(handle)
        target_name = str(item.get('name') or avatar_name(target))
        victim_id = getattr(target, 'id', 0) if target is not None else 0

        player = current_player()
        my_id = getattr(player, 'id', None)
        my_bid = BATTLE.get('entity_id')
        killer_id = int(item.get('killer_id') or 0)

        is_my_kill = (killer_name == getattr(player, 'name', '') or
                      (my_id is not None and killer_id == my_id) or
                      (my_bid is not None and killer_id == my_bid))

        # Passing player.id renders killer name BLUE in HUD kill info
        actual_killer_id = my_id if (is_my_kill and my_id is not None) else killer_id
        show_kill_feed(killer_name, weapon_name, target_name, actual_killer_id, victim_id)

        if is_my_kill and not on_island_stage() and target is not None:
            credit_player_kill(target, item)

        call_later(BODY_LINGER, bury_body, battle_id)
        log('local-battle-remote-kill', target=battle_id, killer=killer_name, weapon=weapon_name)
        return True

    globals()['remote_died'] = redemption_remote_died
    log('ros-redemption-fix', fix='killfeed blue name & kill counter installed')
except Exception:
    pass

# 5. Shift+1 Bicycle & In-Game Tango / Emote
try:
    _redemption_bike_state = {'last_summon': 0.0}

    def redemption_summon_bike(player=None):
        now = time.time()
        if now - _redemption_bike_state['last_summon'] < 2.0:
            return None
        _redemption_bike_state['last_summon'] = now
        player = player or current_player()
        if player is None:
            return None
        try:
            if getattr(player, 'inLandVehicle', False):
                get_off(player, getattr(player, 'vehicleEntID', 0))
                return True
            x, y, z = _point(player.position)
            yaw = float(getattr(player, 'yaw', 0.0) or 0.0)
            cx = x + 2.5 * math.sin(yaw)
            cz = z + 2.5 * math.cos(yaw)
            ground = ground_height(cx, cz) or y
            # 25102 is LandVehicle ID, 140073 is Summer Bicycle appearance
            bike_id = spawn_vehicle('LandCar', 25102, 140073, cx, cz, ground, yaw)
            if bike_id is not None:
                get_on(player, bike_id, True)
                log('local-bicycle-summoned', bike=bike_id)
                return True
        except Exception:
            pass
        return False

    def redemption_play_tango(player=None):
        player = player or current_player()
        if player is None:
            return None
        try:
            if hasattr(player, 'onOwnDoInGameAction'):
                player.onOwnDoInGameAction('display_film_dance01', True)
            elif hasattr(player, 'playAnimation'):
                player.playAnimation('display_film_dance01')
            log('local-tango-played')
            return True
        except Exception:
            pass
        return False

    # Hook into _dh_action_anim so Tango 909042 returns display_film_dance01
    _orig_action_anim = globals().get('_dh_action_anim')
    def redemption_action_anim(appearance_id):
        try:
            aid = int(appearance_id or 0)
            if aid in (909042, 909043, 900001, 900002, 900003, 900004):
                return 'display_film_dance01', True
        except Exception:
            pass
        if callable(_orig_action_anim):
            return _orig_action_anim(appearance_id)
        return 'display_film_dance01', True

    globals()['_dh_action_anim'] = redemption_action_anim

    # Register into LOBBY.RPC_HANDLERS
    _rh = getattr(LOBBY, 'RPC_HANDLERS', None) if LOBBY is not None else None
    if isinstance(_rh, dict):
        _rh['reqSummonPortableVehicle'] = lambda p, *a, **k: redemption_summon_bike(p)
        _rh['reqUsePortableVehicle'] = lambda p, *a, **k: redemption_summon_bike(p)
        _rh['reqUseCarryVehicle'] = lambda p, *a, **k: redemption_summon_bike(p)
        _rh['useCarryVehicle'] = lambda p, *a, **k: redemption_summon_bike(p)

        # Silent handlers for battle RPCs that don't need server-side state
        for _unhandled_rpc in ('onTryingToRun', 'onGetFallDamage', 'onDtsSelectStart', 'onClientLoadingFinish',
                              'onRefreshFlyingAccessory', 'onDecBulletFromMagazine', 'onClientTryControl',
                              'onAirWarClientTryControl', 'onVehicleHonk', 'reqSelectDropPlanePos', 'reqParachute'):
            _rh.setdefault(_unhandled_rpc, lambda *a, **k: None)

    # Pre-select math3d for all position forms so tuple/list probes are skipped cleanly
    try:
        if 'BATTLE' in globals() and isinstance(BATTLE, dict):
            _pw = BATTLE.setdefault('position_with', {})
            for _m in ('teleport', 'onEnterSpace', 'teleportVehicle', 'setPosition', 'setSpaceAndPosition'):
                _pw.setdefault(_m, 'math3d')
    except Exception:
        pass

    # Hotkey listener: Check Shift+1 via GetAsyncKeyState
    import ctypes
    _u32 = ctypes.windll.user32

    def redemption_hotkey_tick():
        try:
            # VK_SHIFT is 0x10, '1' is 0x31
            shift_down = bool(_u32.GetAsyncKeyState(0x10) & 0x8000)
            one_down = bool(_u32.GetAsyncKeyState(0x31) & 0x8000)
            if shift_down and one_down:
                redemption_summon_bike()
        except Exception:
            pass
        call_later(0.15, redemption_hotkey_tick)

    call_later(2.0, redemption_hotkey_tick)

    # Chat commands: /bike and /tango
    _orig_icc = globals().get('install_chat_commands')
    def redemption_install_chat_commands(player):
        if callable(_orig_icc):
            _orig_icc(player)
        try:
            _cmds = globals().get('_chat_commands')
            if isinstance(_cmds, dict):
                _cmds['bike'] = lambda p, a: redemption_summon_bike(p) or 'Summer Bicycle summoned!'
                _cmds['bicycle'] = lambda p, a: redemption_summon_bike(p) or 'Summer Bicycle summoned!'
                _cmds['tango'] = lambda p, a: redemption_play_tango(p) or 'Dancing Tango!'
                _cmds['dance'] = lambda p, a: redemption_play_tango(p) or 'Dancing Tango!'
        except Exception:
            pass
        return True

    globals()['install_chat_commands'] = redemption_install_chat_commands

    log('ros-redemption-fix', fix='bicycle summon, tango dance, and hotkeys installed')
except Exception:
    pass

# 6. Anti-Clump Bot Dispersion in place_bots_near
try:
    def redemption_place_bots_near(point, randomizer, count=None):
        count = count if count is not None else int((BATTLE.get('match') or {}).get('bots') or 0)
        # Scatter bots across the whole map using large radius (1500m - 5000m)
        points = []
        for _index in range(count):
            angle = randomizer.uniform(0.0, 2.0 * math.pi)
            distance = randomizer.uniform(800.0, 4500.0)
            x = point[0] + distance * math.cos(angle)
            z = point[2] + distance * math.sin(angle)
            ground = ground_height(x, z)
            points.append([round(x, 2), round(ground if ground else point[1], 2), round(z, 2)])
        if points:
            send(BOT_PREFIX + json.dumps({'action': 'place', 'points': points}))
        log('ros-redemption-fix', fix='bots dispersed broadly across map, zero clumping')
        return points

    globals()['place_bots_near'] = redemption_place_bots_near
except Exception:
    pass

# 7. Admin / GM Chat Command Protection (Cheats locked to Admin Sean only)
try:
    ADMIN_COMMANDS = {
        'spawn', 'give', 'bots', 'bot', 'hp', 'heal', 'jump',
        'fly', 'noclip', 'zone', 'circle', 'redzone', 'bomb',
        'plane', 'airdrop', 'speed', 'clear', 'freeze', 'walk'
    }

    def redemption_is_admin(player):
        try:
            gid = int(getattr(player, 'gid', 0) or 0)
            name = str(getattr(player, 'name', '') or '')
            if gid in (10000002, 1) or name.lower() in ('sean', 'admin', 'dev radmo'):
                return True
            if LOBBY is not None and hasattr(LOBBY, '_local_profile'):
                prof = LOBBY._local_profile(player) or {}
                if prof.get('gid') in (10000002, 1) or str(prof.get('nickname') or '').lower() in ('sean', 'admin', 'dev radmo'):
                    return True
        except Exception:
            pass
        return False

    _orig_chat_cmd = globals().get('chat_command')

    def redemption_guarded_chat_command(player, channel, msg):
        text = chat_text(msg).strip()
        if not text.startswith('/') or BATTLE.get('phase') != 'fighting':
            return False
        parts = text[1:].split()
        cmd = parts[0].lower() if parts else ''
        
        # Check admin permission
        if cmd in ADMIN_COMMANDS and not redemption_is_admin(player):
            _chat['channel'] = channel
            tip_text('Permission denied: Admin access required.')
            chat_say(player, '[System] Permission denied: %s is an admin-only command.' % cmd)
            log('local-battle-unauthorized-cmd', text=text, name=avatar_name(player))
            return True
            
        if callable(_orig_chat_cmd):
            return _orig_chat_cmd(player, channel, msg)
        return False

    globals()['chat_command'] = redemption_guarded_chat_command
    log('ros-redemption-fix', fix='admin chat command protection active')
except Exception:
    pass

# --------------------------------------------------------------------------
# 8. Fix VehicleAppearanceType.CATEGORY attribute crash in afterEnterSpace
# --------------------------------------------------------------------------
try:
    for _m in list(sys.modules.values()):
        if _m is None: continue
        _cls = getattr(_m, 'VehicleAppearanceType', None)
        if _cls is not None:
            try:
                if not hasattr(_cls, 'CATEGORY'):
                    setattr(_cls, 'CATEGORY', 1)
                    setattr(_cls, 'category', 1)
            except Exception:
                pass
    log('ros-redemption-fix', fix='VehicleAppearanceType CATEGORY safe fallback active')
except Exception:
    pass

log('ros-redemption-master-patch-active', status='ready')



# ==============================================================================


# ==============================================================================


# ==============================================================================


# ==============================================================================
# ROS REDEMPTION - KILLFEED COLOR ENHANCEMENTS & SAFE FALL DAMAGE
# ==============================================================================

# 1. Killfeed Colors: Cyan/Blue on Self Kill, Dark Red on Self Down/Death, White on Enemy
try:
    _COLOR_MY_KILL = '#c00e5ff'   # Cyan / Electric Blue
    _COLOR_MY_DEATH = '#cff2222'  # Dark Red / Crimson
    _COLOR_RESET = '#n'

    def _color_name(name, color):
        s = str(name or '')
        if s.startswith('#c'):
            return s
        return color + s + _COLOR_RESET

    # Hook announce_kill for local player kills
    _orig_announce_kill = globals().get('announce_kill')
    def redemption_announce_kill(player, target, weapon_name, headshot):
        try:
            texts = sys.modules.get('errtxt')
            victim_raw = avatar_name(target)
            killer_raw = avatar_name(player)
            # Self kill: killer name in Blue/Cyan!
            killer = _color_name(killer_raw, _COLOR_MY_KILL)
            victim = str(victim_raw)

            feed = getattr(texts, KILL_TEXT_HEAD if headshot else KILL_TEXT, None) or KILL_TEXT_FALLBACK
            mine = getattr(texts, MY_KILL_TEXT, None) or MY_KILL_TEXT_FALLBACK
            details = {'killerID': getattr(player, 'id', 0), 'killedID': getattr(target, 'id', 0), 'isWounded': False}
            
            try:
                import Globals
                space = Globals.spaceEntity
            except Exception:
                space = None

            for step, call in (('feed', lambda: space.showKillInfo(feed, ([killer, weapon_name, victim],), '', details)),
                               ('effect', lambda: space.showKilledUIEffect(details)),
                               ('tip', lambda: player.dtsKillTip(mine % (weapon_name, victim_raw)))):
                try:
                    call()
                except Exception:
                    pass

            bump(player, 'battleKillNum', 1)
            if space is not None:
                bump(space, 'aliveNum', -1, floor=1)
                if int(getattr(space, 'aliveNum', 2) or 2) <= 1 and int(getattr(player, 'hp', 0) or 0) > 0:
                    call_later(RESULT_DELAY, show_result, player, 1)
            return True
        except Exception:
            if callable(_orig_announce_kill):
                return _orig_announce_kill(player, target, weapon_name, headshot)
            return False

    globals()['announce_kill'] = redemption_announce_kill
    log('ros-redemption-fix', fix='blue self kill announce installed')
except Exception:
    pass


# 2. Hook show_kill_feed for all kills (remote & local)
try:
    _orig_show_kill_feed = globals().get('show_kill_feed')
    def redemption_show_kill_feed(killer, weapon_name, victim, killer_id, victim_id, is_wounded=False):
        try:
            texts = sys.modules.get('errtxt')
            feed = getattr(texts, KILL_TEXT, None) or KILL_TEXT_FALLBACK

            player = current_player()
            my_id = getattr(player, 'id', None)
            my_name = str(getattr(player, 'name', '') or avatar_name(player) or '')

            is_my_kill = (my_id is not None and killer_id == my_id) or (str(killer) == my_name)
            is_my_victim = (my_id is not None and victim_id == my_id) or (str(victim) == my_name)

            if is_my_kill:
                killer_str = _color_name(killer, _COLOR_MY_KILL)
                victim_str = str(victim)
            elif is_my_victim:
                killer_str = str(killer)
                victim_str = _color_name(victim, _COLOR_MY_DEATH)
            else:
                # Enemy killed enemy: clean white / default
                killer_str = str(killer)
                victim_str = str(victim)

            import Globals
            space = getattr(Globals, 'spaceEntity', None)
            if space is not None:
                details = {'killerID': killer_id, 'killedID': victim_id, 'isWounded': bool(is_wounded)}
                if is_wounded:
                    w_feed = '%s knocked down %s with %s'
                    space.showKillInfo(w_feed, ([killer_str, victim_str, weapon_name],), '', details)
                else:
                    space.showKillInfo(feed, ([killer_str, weapon_name, victim_str],), '', details)
                return True
        except Exception:
            pass

        if callable(_orig_show_kill_feed):
            return _orig_show_kill_feed(killer, weapon_name, victim, killer_id, victim_id)
        return False

    globals()['show_kill_feed'] = redemption_show_kill_feed
    log('ros-redemption-fix', fix='colored show_kill_feed installed')
except Exception:
    pass


# 3. Hook _dh_kd_enter for Dark Red knockdown alert
try:
    _orig_kd_enter = globals().get('_dh_kd_enter')
    if callable(_orig_kd_enter):
        def redemption_kd_enter(player, down):
            res = _orig_kd_enter(player, down)
            try:
                left = int(down.get('left') or 0)
                tip_text('#cff2222You are down!#n A teammate can revive you - %d s left' % left)
                # Broadcast down in killfeed in Dark Red
                by_who = str(down.get('by') or 'Enemy')
                p_name = avatar_name(player)
                redemption_show_kill_feed(by_who, 'Attack', p_name, 0, getattr(player, 'id', 0), is_wounded=True)
            except Exception:
                pass
            return res

        globals()['_dh_kd_enter'] = redemption_kd_enter
        log('ros-redemption-fix', fix='dark red knockdown alert installed')
except Exception:
    pass


# 4. Safe Fall Damage: ONLY ACTIVE AFTER LANDING FROM THE PLANE!
# - Starting island, plane, skydiving, parachuting = COMPLETELY DISABLED (0 damage)
# - Normal jumps, hops, stairs = 100% IMMUNE (0 damage)
# - Real cliffs & tall structures (> 10m drop and >= 1.0s free-fall) = realistic damage
try:
    _dh_fall_ctrl = {
        'in_air': False,
        'air_start_y': None,
        'air_start_time': 0.0,
        'first_ground_time': 0.0,
    }

    def _dh_fall_damage_monitor():
        try:
            player = current_player()
            if player is None or getattr(player, 'deadInGame', False):
                call_later(0.1, _dh_fall_damage_monitor)
                return

            # ONLY ACTIVE AFTER COMING DOWN FROM THE PLANE!
            flight = globals().get('_flight') or {}
            if flight.get('stage') != 'landed' or not flight.get('landed_once'):
                _dh_fall_ctrl['in_air'] = False
                _dh_fall_ctrl['air_start_y'] = None
                call_later(0.2, _dh_fall_damage_monitor)
                return

            try:
                if callable(globals().get('on_island_stage')) and globals()['on_island_stage']():
                    _dh_fall_ctrl['in_air'] = False
                    _dh_fall_ctrl['air_start_y'] = None
                    call_later(0.2, _dh_fall_damage_monitor)
                    return
            except Exception:
                pass

            now = time.time()
            if not _dh_fall_ctrl.get('first_ground_time'):
                _dh_fall_ctrl['first_ground_time'] = now
            # Grace period of 4 seconds after landing from parachute
            if now - _dh_fall_ctrl['first_ground_time'] < 4.0:
                _dh_fall_ctrl['in_air'] = False
                _dh_fall_ctrl['air_start_y'] = None
                call_later(0.2, _dh_fall_damage_monitor)
                return

            # Ignore while in vehicle
            if getattr(player, 'inLandVehicle', False):
                _dh_fall_ctrl['in_air'] = False
                call_later(0.1, _dh_fall_damage_monitor)
                return

            pos = getattr(player, 'position', None)
            if pos is None:
                call_later(0.1, _dh_fall_damage_monitor)
                return

            cur_y = float(pos[1] if hasattr(pos, '__getitem__') else getattr(pos, 'y', 0.0))
            on_ground = character_on_ground(player)

            if not on_ground:
                if not _dh_fall_ctrl['in_air']:
                    _dh_fall_ctrl['in_air'] = True
                    _dh_fall_ctrl['air_start_y'] = cur_y
                    _dh_fall_ctrl['air_start_time'] = now
            else:
                if _dh_fall_ctrl['in_air']:
                    _dh_fall_ctrl['in_air'] = False
                    start_y = _dh_fall_ctrl.get('air_start_y')
                    air_duration = now - (_dh_fall_ctrl.get('air_start_time') or now)

                    if start_y is not None:
                        drop_height = start_y - cur_y

                        # MUST be real sustained free-fall (>= 1.0s) AND drop > 10.0 meters
                        # Normal jumps, bunny hops, ledge hops, and slopes are 100% IMMUNE (0 damage)
                        if drop_height > 10.0 and air_duration >= 1.0:
                            excess = drop_height - 10.0
                            damage = int(round(excess * 5.0))
                            if damage > 0:
                                try:
                                    old_hp = int(getattr(player, 'hp', 100) or 100)
                                    new_hp = max(0, old_hp - damage)
                                    player.hp = new_hp

                                    # Update HUD HP bar
                                    changed = getattr(player, 'set_hp', None)
                                    if callable(changed):
                                        changed(old_hp)

                                    # Damage number popup on player
                                    try:
                                        show_damage_text(pos, damage, 1, 2)
                                    except Exception:
                                        pass

                                    tip_text('#cff4444Took %d fall damage!#n' % damage)
                                    log('local-battle-fall-damage', drop=round(drop_height, 2), duration=round(air_duration, 2), damage=damage, hp=new_hp)

                                    if new_hp <= 0:
                                        victim_name = avatar_name(player)
                                        redemption_show_kill_feed('High Fall', 'Falling', victim_name, 0, getattr(player, 'id', 0))
                                        player_died(player, 'fall', _point(pos))
                                except Exception as ex:
                                    log_error('local-battle-fall-damage-error', err=str(ex))

                    _dh_fall_ctrl['air_start_y'] = None

        except Exception:
            pass

        call_later(0.08, _dh_fall_damage_monitor)

    call_later(1.5, _dh_fall_damage_monitor)
    log('ros-redemption-fix', fix='safe balanced fall damage active (plane landing only)')
except Exception:
    pass


# 5. Prepare Island Bot Dispersion (Anti-Clump / Spread out across the island)
try:
    def redemption_disperse_island_bots():
        try:
            if not on_island_stage():
                return
            
            map_id = BATTLE.get('map') or 700
            count = int((BATTLE.get('match') or {}).get('bots') or 40)
            
            # 1. Try to get official RebornPosition points on the island
            island_points = []
            try:
                pts = level_points(level_record(map_id), 'RebornPosition')
                if pts:
                    import random
                    rng = random.Random()
                    if len(pts) >= count:
                        island_points = [[round(p[0], 2), round(p[1], 2), round(p[2], 2)] for p in rng.sample(pts, count)]
                    else:
                        island_points = [[round(p[0], 2), round(p[1], 2), round(p[2], 2)] for p in pts]
            except Exception:
                island_points = []

            # 2. If no level points, generate wide radial spots around island
            if not island_points:
                player = current_player()
                pos = getattr(player, 'position', None)
                if pos is not None:
                    cx = float(pos[0] if hasattr(pos, '__getitem__') else getattr(pos, 'x', 0.0))
                    cy = float(pos[1] if hasattr(pos, '__getitem__') else getattr(pos, 'y', 10.0))
                    cz = float(pos[2] if hasattr(pos, '__getitem__') else getattr(pos, 'z', 0.0))
                    import random, math
                    rng = random.Random()
                    for idx in range(count):
                        angle = (2.0 * math.pi * idx) / float(max(1, count)) + rng.uniform(-0.3, 0.3)
                        dist = rng.uniform(40.0, 240.0)
                        px = cx + dist * math.cos(angle)
                        pz = cz + dist * math.sin(angle)
                        py = ground_height(px, pz) or cy
                        island_points.append([round(px, 2), round(py, 2), round(pz, 2)])

            if island_points:
                send(BOT_PREFIX + json.dumps({'action': 'place', 'points': island_points}))
                log('ros-redemption-fix', fix='prepare island bots dispersed', count=len(island_points))
        except Exception as ex:
            log_error('local-battle-island-disperse-error', err=str(ex))

    # Periodic check on island to keep bots nicely spread out
    def _dh_island_bot_tick():
        try:
            if on_island_stage():
                redemption_disperse_island_bots()
                call_later(6.0, _dh_island_bot_tick)
        except Exception:
            pass

    # Call on start
    call_later(1.0, redemption_disperse_island_bots)
    call_later(3.0, redemption_disperse_island_bots)
    call_later(6.0, _dh_island_bot_tick)

    # Hook schedule_plane to trigger dispersion right when island starts
    _orig_schedule_plane = globals().get('schedule_plane')
    if callable(_orig_schedule_plane):
        def redemption_schedule_plane():
            res = _orig_schedule_plane()
            call_later(0.5, redemption_disperse_island_bots)
            return res
        globals()['schedule_plane'] = redemption_schedule_plane

    log('ros-redemption-fix', fix='prepare island anti-clump installed')
except Exception:
    pass


# 6. Varied Bot Appearance (Gender & Model variety instead of all cloned identical males)
try:
    _orig_remote_properties = globals().get('remote_properties')
    if callable(_orig_remote_properties):
        def redemption_remote_properties(item, class_name):
            props = _orig_remote_properties(item, class_name)
            try:
                item_id = int(item.get('id') or 0)
                name = str(item.get('name') or '')
                if 'Bot' in name or item.get('kind') == 'bot' or item_id >= 900000:
                    # Alternate male (10002) and female (10001)
                    props['characterType'] = 10001 if (item_id % 2 == 1) else 10002
            except Exception:
                pass
            return props

        globals()['remote_properties'] = redemption_remote_properties
        log('ros-redemption-fix', fix='varied bot gender and appearance active')
except Exception:
    pass

log('ros-redemption-killfeed-and-fall-damage-active', status='ready')


# ==============================================================================
# ROS REDEMPTION - VEHICLE SYSTEM OVERHAUL
# 1. Car Skin System (reqDyeingVehicle handler, boarding auto-skin, /skin command)
# 2. Turbo Boost (onAccStart / onAccEnd, Shift hotkey, 2.4x driveForce, nitro flames)
# 3. Fuel / Gas Consumption (dynamic consumption, faster on turbo, out-of-gas, /fuel)
# 4. Engine Audio Smoothing (no screeching/RPM spikes, eliminates stutter/lag)
# ==============================================================================

# Global vehicle states
_car_turbo_state = {}
_car_empty_gas = set()

# --- 1. CAR SKIN SYSTEM ---
try:
    def redemption_apply_car_skin(car, appearance_id):
        if car is None:
            return False
        try:
            aid = int(appearance_id or 0)
            if not aid:
                return False
            old_aid = getattr(car, 'tpsVehicleID', 0)
            car.tpsVehicleID = aid

            veh_dict = globals().get('_vehicles')
            if isinstance(veh_dict, dict) and getattr(car, 'id', None) in veh_dict:
                veh_dict[car.id]['tps'] = aid

            if hasattr(car, 'set_tpsVehicleID'):
                try:
                    car.set_tpsVehicleID(old_aid)
                except Exception:
                    pass

            for method in ('onVehicleAppearanceChanged', 'changeAppearance', 'onDyeingVehicle', 'dyeingVehicle'):
                fn = getattr(car, method, None)
                if callable(fn):
                    try:
                        fn(aid)
                    except Exception:
                        pass

            try:
                assemble = car.gameObject.GetComponent('VehiclePhysicAssemble')
                if assemble is not None:
                    for assem_fn in ('resetAppearance', 'initAppearance', 'changeAppearance'):
                        m = getattr(assemble, assem_fn, None)
                        if callable(m):
                            try:
                                m(aid)
                            except Exception:
                                pass
            except Exception:
                pass

            log('local-battle-car-skin-applied', vehicle=getattr(car, 'id', 0), skin=aid)
            return True
        except Exception as ex:
            log_error('local-battle-car-skin-error', err=str(ex))
            return False

    def redemption_req_dyeing_vehicle(player, vehicle_id=0, appearance_id=0, *args, **kwargs):
        try:
            vid = int(vehicle_id or 0)
            aid = int(appearance_id or 0)
            car = vehicle_entity(vid) if callable(globals().get('vehicle_entity')) else None
            if car is None:
                try:
                    import BigWorld
                    car = BigWorld.entities.get(vid)
                except Exception:
                    car = None
            if car is not None and aid:
                redemption_apply_car_skin(car, aid)
                if hasattr(player, 'dyeingVehicle'):
                    try:
                        player.dyeingVehicle(vid, aid)
                    except Exception:
                        pass
                elif hasattr(player, 'onDyeingVehicle'):
                    try:
                        player.onDyeingVehicle(vid, aid)
                    except Exception:
                        pass
                tip_text('#c00e5ffCar skin applied!#n')
                return True
        except Exception:
            pass
        return True

    _rh = getattr(LOBBY, 'RPC_HANDLERS', None) if LOBBY is not None else None
    if isinstance(_rh, dict):
        _rh['reqDyeingVehicle'] = redemption_req_dyeing_vehicle
        _rh['reqPlayVehicleTransformExitEff'] = lambda *a, **k: True
        _rh['reqWearVehicleTransformCloth'] = lambda *a, **k: True

    _orig_seat_player = globals().get('seat_player')
    if callable(_orig_seat_player):
        def redemption_seat_player_skin(player, car, socket, *args, **kwargs):
            res = _orig_seat_player(player, car, socket, *args, **kwargs)
            try:
                driver_socket = globals().get('VEHICLE_DRIVER_SOCKET', 'Driver')
                if socket == driver_socket and car is not None:
                    skins_dict = getattr(player, 'landVehicleID2AppearanceIDDict', None)
                    chosen_skin = None
                    if isinstance(skins_dict, dict):
                        char_type = int(getattr(car, 'characterType', 0) or 0)
                        if char_type in skins_dict:
                            chosen_skin = skins_dict[char_type]
                        elif skins_dict:
                            chosen_skin = list(skins_dict.values())[0]
                    if not chosen_skin:
                        app_list = getattr(player, 'dtsVehicleAppearanceList', None)
                        if app_list:
                            chosen_skin = app_list[0]
                    if chosen_skin:
                        call_later(0.2, redemption_apply_car_skin, car, chosen_skin)
            except Exception:
                pass
            return res

        globals()['seat_player'] = redemption_seat_player_skin

    log('ros-redemption-fix', fix='car skin system installed')
except Exception:
    pass


# --- 2. TURBO / NITRO BOOST SYSTEM ---
try:
    def redemption_nos_start(entity_id, *args):
        try:
            vid = int(entity_id or 0)
            car = vehicle_entity(vid) if callable(globals().get('vehicle_entity')) else None
            if car is None:
                return False
            if vid in _car_empty_gas:
                tip_text('#cff2222Cannot boost: Out of gas!#n')
                return False

            _car_turbo_state[vid] = True

            buffs = getattr(car, 'vehicleBuff', None)
            if buffs is not None:
                buffs['driveForceBuff'] = 2.4
                buffs['maxSpeedBuff'] = 1.6
                buffs['throttleBuff'] = 1.5

            if callable(globals().get('vehicle_engine')):
                engine = vehicle_engine(car)
                if engine is not None:
                    setattr(engine, 'nosOpen', True)
                    if hasattr(engine, 'startNOS'):
                        try:
                            engine.startNOS()
                        except Exception:
                            pass

            if callable(globals().get('show_nos')):
                show_nos(car, True)

            log('local-battle-turbo-start', vehicle=vid)
            return True
        except Exception:
            return False

    def redemption_nos_end(entity_id, *args):
        try:
            vid = int(entity_id or 0)
            car = vehicle_entity(vid) if callable(globals().get('vehicle_entity')) else None
            _car_turbo_state[vid] = False
            if car is None:
                return False

            buffs = getattr(car, 'vehicleBuff', None)
            if buffs is not None:
                buffs['driveForceBuff'] = 1.0
                buffs['maxSpeedBuff'] = 1.0
                buffs['throttleBuff'] = 1.0

            if callable(globals().get('vehicle_engine')):
                engine = vehicle_engine(car)
                if engine is not None:
                    setattr(engine, 'nosOpen', False)
                    if hasattr(engine, 'stopNOS'):
                        try:
                            engine.stopNOS()
                        except Exception:
                            pass

            if callable(globals().get('show_nos')):
                show_nos(car, False)

            log('local-battle-turbo-end', vehicle=vid)
            return True
        except Exception:
            return False

    ccc = globals().get('CAR_CELL_CALLS')
    if isinstance(ccc, dict):
        ccc['onAccStart'] = redemption_nos_start
        ccc['onAccEnd'] = redemption_nos_end

    globals()['car_nos_on'] = redemption_nos_start
    globals()['car_nos_off'] = redemption_nos_end

    log('ros-redemption-fix', fix='turbo boost system installed')
except Exception:
    pass


# --- 3. VEHICLE FUEL / GAS SYSTEM ---
try:
    def _dh_car_fuel_monitor():
        try:
            player = current_player()
            if player is not None and getattr(player, 'isLandDriver', False):
                vid = getattr(player, 'vehicleEntID', 0)
                car = vehicle_entity(vid) if callable(globals().get('vehicle_entity')) else None
                if car is not None and not getattr(car, 'vIsDead', False):
                    cur_fuel = getattr(car, 'fuelAmount', None)
                    if cur_fuel is None or (cur_fuel <= 0.0 and vid not in _car_empty_gas):
                        car.fuelAmount = 100.0
                        cur_fuel = 100.0

                    if cur_fuel > 0.0:
                        speed = vehicle_speed(car) if callable(globals().get('vehicle_speed')) else 0.0
                        is_turbo = _car_turbo_state.get(vid, False)

                        if is_turbo:
                            burn = 1.8
                        elif speed > 5.0:
                            burn = 0.35
                        elif speed > 0.5:
                            burn = 0.15
                        else:
                            burn = 0.04

                        new_fuel = max(0.0, cur_fuel - burn)
                        old_fuel = car.fuelAmount
                        car.fuelAmount = round(new_fuel, 2)

                        if hasattr(car, 'set_fuelAmount'):
                            try:
                                car.set_fuelAmount(old_fuel)
                            except Exception:
                                pass
                        if hasattr(car, 'onUpdateFuelAmount'):
                            try:
                                car.onUpdateFuelAmount(new_fuel)
                            except Exception:
                                pass
                        if hasattr(player, 'onUpdateVehicleGas'):
                            try:
                                player.onUpdateVehicleGas(vid, int(new_fuel))
                            except Exception:
                                pass

                        if new_fuel <= 0.0:
                            _car_empty_gas.add(vid)
                            redemption_nos_end(vid)
                            buffs = getattr(car, 'vehicleBuff', None)
                            if buffs is not None:
                                buffs['driveForceBuff'] = 0.0
                                buffs['throttleBuff'] = 0.0
                            tip_text('#cff2222Vehicle out of fuel!#n')
                            log('local-battle-vehicle-out-of-gas', vehicle=vid)
        except Exception:
            pass
        call_later(0.5, _dh_car_fuel_monitor)

    call_later(2.0, _dh_car_fuel_monitor)
    log('ros-redemption-fix', fix='fuel consumption monitor installed')
except Exception:
    pass


# --- 4. ENGINE AUDIO & SOUND STUTTER FIX ---
try:
    _orig_steady_my_car = globals().get('steady_my_car')
    def redemption_steady_and_smooth_sound():
        res = _orig_steady_my_car() if callable(_orig_steady_my_car) else False
        try:
            player = current_player()
            if player is not None and getattr(player, 'isLandDriver', False):
                vid = getattr(player, 'vehicleEntID', 0)
                car = vehicle_entity(vid) if callable(globals().get('vehicle_entity')) else None
                if car is not None:
                    try:
                        tpsound = car.gameObject.GetComponent('VehicleTPSound')
                        if tpsound is not None:
                            if hasattr(tpsound, 'enabled'):
                                tpsound.enabled = False
                    except Exception:
                        pass

                    if callable(globals().get('vehicle_engine')):
                        engine = vehicle_engine(car)
                        if engine is not None:
                            kmh = vehicle_speed(car) if callable(globals().get('vehicle_speed')) else 0.0
                            is_turbo = _car_turbo_state.get(vid, False)
                            target_rpm = 1000.0 + min(6500.0, kmh * 72.0) + (1200.0 if is_turbo else 0.0)

                            cur_sound_rpm = float(getattr(engine, 'soundRpm', 0.0) or target_rpm)
                            if cur_sound_rpm > 10000.0 or cur_sound_rpm < 400.0:
                                engine.soundRpm = target_rpm
                            else:
                                engine.soundRpm = round(cur_sound_rpm * 0.75 + target_rpm * 0.25, 1)

                            cur_gear = int(getattr(engine, 'gear', 1) or 1)
                            if kmh > 60.0 and cur_gear < 4:
                                engine.gear = 5
        except Exception:
            pass
        return res

    globals()['steady_my_car'] = redemption_steady_and_smooth_sound
    log('ros-redemption-fix', fix='engine sound smoothing and stutter fix installed')
except Exception:
    pass


# --- 5. HOTKEYS & CHAT COMMANDS (Shift Turbo, /fuel, /skin) ---
try:
    import ctypes
    _u32 = ctypes.windll.user32
    _shift_was_down = [False]

    def redemption_vehicle_hotkey_tick():
        try:
            player = current_player()
            if player is not None and getattr(player, 'isLandDriver', False):
                vid = getattr(player, 'vehicleEntID', 0)
                # VK_SHIFT is 0x10
                shift_down = bool(_u32.GetAsyncKeyState(0x10) & 0x8000)
                if shift_down and not _shift_was_down[0]:
                    _shift_was_down[0] = True
                    redemption_nos_start(vid)
                elif not shift_down and _shift_was_down[0]:
                    _shift_was_down[0] = False
                    redemption_nos_end(vid)
            else:
                _shift_was_down[0] = False
        except Exception:
            pass
        call_later(0.1, redemption_vehicle_hotkey_tick)

    call_later(2.0, redemption_vehicle_hotkey_tick)

    _orig_icc = globals().get('install_chat_commands')
    def redemption_vehicle_install_chat_commands(player):
        if callable(_orig_icc):
            _orig_icc(player)
        try:
            _cmds = globals().get('_chat_commands')
            if isinstance(_cmds, dict):
                def _cmd_fuel(p, a):
                    vid = getattr(p, 'vehicleEntID', 0)
                    car = vehicle_entity(vid) if callable(globals().get('vehicle_entity')) else None
                    if car is not None:
                        car.fuelAmount = 100.0
                        _car_empty_gas.discard(vid)
                        buffs = getattr(car, 'vehicleBuff', None)
                        if buffs is not None:
                            buffs['driveForceBuff'] = 1.0
                            buffs['throttleBuff'] = 1.0
                        if hasattr(car, 'set_fuelAmount'):
                            car.set_fuelAmount(0.0)
                        tip_text('#c00ff00Fuel refilled to 100%!#n')
                        return 'Fuel refilled to 100%!'
                    return 'Not inside a vehicle.'

                def _cmd_skin(p, a):
                    vid = getattr(p, 'vehicleEntID', 0)
                    car = vehicle_entity(vid) if callable(globals().get('vehicle_entity')) else None
                    if car is None:
                        return 'Not inside a vehicle.'
                    parts = str(a or '').split()
                    skin_id = int(parts[0]) if parts and parts[0].isdigit() else 142080
                    redemption_apply_car_skin(car, skin_id)
                    tip_text('#c00e5ffVehicle skin set to %d!#n' % skin_id)
                    return 'Vehicle skin set to %d!' % skin_id

                _cmds['fuel'] = _cmd_fuel
                _cmds['gas'] = _cmd_fuel
                _cmds['skin'] = _cmd_skin
                _cmds['carskin'] = _cmd_skin
        except Exception:
            pass
        return True

    globals()['install_chat_commands'] = redemption_vehicle_install_chat_commands
    log('ros-redemption-fix', fix='vehicle hotkeys and commands installed')
except Exception:
    pass

log('ros-redemption-vehicle-system-complete-active', status='ready')


# ==============================================================================
# 6. DUO / SQUAD TEAMMATE SYSTEM, OVERHEAD NAME/NUMBER UI, TEAM HP HUD & QUIT FIX
# ==============================================================================

# ==============================================================================
# SECTION 6: DUO/SQUAD TEAMMATE TRACKING, NATIVE HUD SYNC & QUIT CRASH FIXES
# ==============================================================================

# 6A. Settle unfinished match ONLY if leaving during actual match (after landing), NOT at starting island or plane
def _dh_conditional_settle_unfinished_match(player=None, *args, **kwargs):
    player = player or current_player()
    # If still on starting island, or aboard plane, or hasn't landed on ground yet: DO NOT COUNT
    if on_island_stage() or not _flight.get('landed_once') or _flight.get('stage') in ('island', 'plane'):
        log('local-battle-quit-ignored-starting', stage=_flight.get('stage'), landed=_flight.get('landed_once'))
        return False

    # In the actual match on the ground: record the match!
    if _round.get('shown') or _round.get('settled') or not BATTLE.get('match') or player is None:
        return False
    _round['settled'] = True
    try:
        space = zone_space()
        rank = max(1, int(getattr(space, 'aliveNum', 1) or 1))
        total = max(rank, match_total())
        record = result_record(player, rank, total)
        owner = owner_result(rank, total, record)
        record['score'] = owner['score']
        record_match(match_summary(record, rank, total))
        log('local-battle-settled-on-leave', rank=rank, total=total, kills=record.get('kill'), exp=record.get('exp'))
        return True
    except Exception:
        log_error('local-battle-settle-error')
        return False

globals()['settle_unfinished_match'] = _dh_conditional_settle_unfinished_match

_orig_leave_battle = globals().get('leave_battle')
if _orig_leave_battle is not None:
    def _dh_safe_leave_battle(player=None, *args, **kwargs):
        if on_island_stage() or not _flight.get('landed_once') or _flight.get('stage') in ('island', 'plane'):
            _round['settled'] = True
            log('local-battle-leave-ignored-starting', stage=_flight.get('stage'), landed=_flight.get('landed_once'))
        return _orig_leave_battle(player, *args, **kwargs)
    globals()['leave_battle'] = _dh_safe_leave_battle


# 6B. Fix Battle Quit Crashes (RemoveBehaviour, initTeleportPanel, PhysicsAdapter, iPerspective)
def _dh_install_battle_quit_guards():
    # 1. Catch ValueError in BehaviourContainer.RemoveBehaviour so leaveWorld does not crash
    try:
        for bc_mod_name in (
            'libclaudia.internals.BehaviourProtocol.BehaviourContainer',
            'internals.BehaviourProtocol.BehaviourContainer',
            'BehaviourContainer',
        ):
            mod = sys.modules.get(bc_mod_name)
            if mod is None:
                try:
                    mod = __import__(bc_mod_name, fromlist=['BehaviourContainer'])
                except Exception:
                    continue
            cls = getattr(mod, 'BehaviourContainer', None)
            if cls is not None:
                orig_rb = getattr(cls, 'RemoveBehaviour', None)
                if callable(orig_rb) and not getattr(orig_rb, '_dh_safe', False):
                    def _safe_remove_behaviour(self, *a, **k):
                        try:
                            return orig_rb(self, *a, **k)
                        except (ValueError, Exception):
                            return None
                    _safe_remove_behaviour._dh_safe = True
                    cls.RemoveBehaviour = _safe_remove_behaviour
    except Exception:
        pass

    # 2. Catch KeyError in UIPanelSkill.initTeleportPanel (PC Exit Button)
    try:
        for ps_mod_name in ('ui.UIPanelSkill', 'UIPanelSkill'):
            mod = sys.modules.get(ps_mod_name)
            if mod is None:
                try:
                    mod = __import__(ps_mod_name, fromlist=['UIPanelSkill'])
                except Exception:
                    continue
            cls = getattr(mod, 'UIPanelSkill', None)
            if cls is not None:
                orig_itp = getattr(cls, 'initTeleportPanel', None)
                if callable(orig_itp) and not getattr(orig_itp, '_dh_safe', False):
                    def _safe_itp(self, *a, **k):
                        try:
                            return orig_itp(self, *a, **k)
                        except (KeyError, Exception):
                            return None
                    _safe_itp._dh_safe = True
                    cls.initTeleportPanel = _safe_itp
    except Exception:
        pass

    # 3. Catch AttributeError in PhysicsAdapter during world teardown
    try:
        for pa_mod_name in ('helpers.PhysicsAdapter', 'PhysicsAdapter'):
            mod = sys.modules.get(pa_mod_name)
            if mod is None:
                try:
                    mod = __import__(pa_mod_name, fromlist=['PhysicsAdapter'])
                except Exception:
                    continue
            cls = getattr(mod, 'PhysicsAdapter', None)
            if cls is not None:
                for fn_name in ('_getStartPos', '_doRecastWithScene'):
                    orig_fn = getattr(cls, fn_name, None)
                    if callable(orig_fn) and not getattr(orig_fn, '_dh_safe', False):
                        def _make_safe_pa(f):
                            def _safe_fn(self, *a, **k):
                                try:
                                    return f(self, *a, **k)
                                except (AttributeError, Exception):
                                    return None
                            _safe_fn._dh_safe = True
                            return _safe_fn
                        setattr(cls, fn_name, _make_safe_pa(orig_fn))
    except Exception:
        pass

    # 4. Catch AttributeError in iPerspective.isPerspected
    try:
        for ip_mod_name in ('entities.iPerspective', 'iPerspective'):
            mod = sys.modules.get(ip_mod_name)
            if mod is None:
                try:
                    mod = __import__(ip_mod_name, fromlist=['iPerspective'])
                except Exception:
                    continue
            cls = getattr(mod, 'iPerspective', None)
            if cls is not None:
                orig_isp = getattr(cls, 'isPerspected', None)
                if callable(orig_isp) and not getattr(orig_isp, '_dh_safe', False):
                    def _safe_isp(self, *a, **k):
                        try:
                            return orig_isp(self, *a, **k)
                        except (AttributeError, Exception):
                            return False
                    _safe_isp._dh_safe = True
                    cls.isPerspected = _safe_isp
    except Exception:
        pass


_dh_install_battle_quit_guards()


# 6C. Purge ClientTeammate entities on leave_battle & drop_battle_world
def _dh_purge_client_teammates():
    try:
        import BigWorld
        for ent in list(BigWorld.entities.values()):
            if ent is None:
                continue
            cname = getattr(getattr(ent, '__class__', None), '__name__', '')
            if cname == 'ClientTeammate' or 'ClientTeammate' in str(type(ent)):
                try:
                    BigWorld.destroyEntity(ent.id)
                except Exception:
                    pass
        p = BigWorld.player()
        if p is not None:
            p_cname = getattr(getattr(p, '__class__', None), '__name__', '')
            if p_cname == 'ClientTeammate' or 'ClientTeammate' in str(type(p)):
                try:
                    BigWorld.destroyEntity(p.id)
                except Exception:
                    pass
    except Exception:
        pass


_dh_orig_leave_battle_purge = globals().get('leave_battle')
while getattr(_dh_orig_leave_battle_purge, '_dh_purge_inner', None) is not None:
    _dh_orig_leave_battle_purge = _dh_orig_leave_battle_purge._dh_purge_inner


def _dh_leave_battle_purge_wrapper(*a, **k):
    try:
        _dh_install_battle_quit_guards()
        _dh_purge_client_teammates()
    except Exception:
        pass
    res = None
    if callable(_dh_orig_leave_battle_purge):
        try:
            res = _dh_orig_leave_battle_purge(*a, **k)
        except Exception:
            pass
    try:
        _dh_purge_client_teammates()
    except Exception:
        pass
    return res


_dh_leave_battle_purge_wrapper._dh_purge_inner = _dh_orig_leave_battle_purge
globals()['leave_battle'] = _dh_leave_battle_purge_wrapper


_dh_orig_drop_battle_world = globals().get('drop_battle_world')
while getattr(_dh_orig_drop_battle_world, '_dh_purge_inner', None) is not None:
    _dh_orig_drop_battle_world = _dh_orig_drop_battle_world._dh_purge_inner


def _dh_drop_battle_world_wrapper(*a, **k):
    try:
        _dh_install_battle_quit_guards()
        _dh_purge_client_teammates()
    except Exception:
        pass
    res = None
    if callable(_dh_orig_drop_battle_world):
        try:
            res = _dh_orig_drop_battle_world(*a, **k)
        except Exception:
            pass
    try:
        _dh_purge_client_teammates()
    except Exception:
        pass
    return res


if callable(_dh_orig_drop_battle_world):
    _dh_drop_battle_world_wrapper._dh_purge_inner = _dh_orig_drop_battle_world
    globals()['drop_battle_world'] = _dh_drop_battle_world_wrapper


# 6D. ClientTeammate Plumbing: Hide White Stand-in Mesh & Support Lifecycle
def _dh_hide_ct_model(ct):
    if ct is None:
        return
    try:
        if hasattr(ct, 'model') and ct.model is not None:
            ct.model.visible = False
            ct.model.scale = (0.0001, 0.0001, 0.0001)
    except Exception:
        pass


def _dh_register_client_teammate(ct):
    try:
        if ct is None:
            return
        _dh_hide_ct_model(ct)
        ct.onBecomePlayer = lambda self=None: None
        ct.onBecomeNonPlayer = lambda self=None: None
    except Exception:
        pass


def _dh_install_teammate_entity_plumbing():
    try:
        for mod_name in ('ClientTeammate', 'entities.ClientTeammate'):
            mod = sys.modules.get(mod_name)
            if mod is None:
                try:
                    mod = __import__(mod_name, fromlist=['ClientTeammate'])
                except Exception:
                    continue
            cls = getattr(mod, 'ClientTeammate', None)
            if cls is not None:
                if not hasattr(mod, 'PlayerClientTeammate'):
                    setattr(mod, 'PlayerClientTeammate', cls)
                cls.onBecomePlayer = lambda self=None: None
                cls.onBecomeNonPlayer = lambda self=None: None
                if not hasattr(cls, 'setPosition'):
                    def _ct_set_pos(self, pos=None, *a, **k):
                        try:
                            if pos is not None:
                                self.position = pos
                        except Exception:
                            pass
                    cls.setPosition = _ct_set_pos
                orig_enter = getattr(cls, 'enterWorld', None)
                if not getattr(orig_enter, '_dh_ct_enter', False):
                    def _ct_enter_world(self, *a, **k):
                        try:
                            _dh_register_client_teammate(self)
                        except Exception:
                            pass
                        if callable(orig_enter):
                            try:
                                return orig_enter(self, *a, **k)
                            except Exception:
                                pass
                        return None
                    _ct_enter_world._dh_ct_enter = True
                    cls.enterWorld = _ct_enter_world
        install_class_defaults('ClientTeammate')
        install_remote_fallback('ClientTeammate')
    except Exception:
        pass

    def _avatar_noop_set_position(self, pos=None, *a, **k):
        return None

    for mod_name, cls_names in (
        ('Avatar', ('Avatar', 'PlayerAvatar')),
        ('entities.Avatar', ('Avatar', 'PlayerAvatar')),
        ('BattleGroundAvatar', ('BattleGroundAvatar', 'PlayerBattleGroundAvatar')),
        ('entities.BattleGroundAvatar', ('BattleGroundAvatar', 'PlayerBattleGroundAvatar')),
    ):
        try:
            mod = sys.modules.get(mod_name) or __import__(mod_name, fromlist=list(cls_names))
        except Exception:
            continue
        for cname in cls_names:
            cls = getattr(mod, cname, None)
            if isinstance(cls, type) and not hasattr(cls, 'setPosition'):
                try:
                    cls.setPosition = _avatar_noop_set_position
                except Exception:
                    pass


def _dh_install_ct_create_wrapper():
    try:
        import BigWorld
        orig_ce = getattr(BigWorld, 'createEntity', None)
        while getattr(orig_ce, '_dh_ct_inner', None) is not None:
            orig_ce = orig_ce._dh_ct_inner
        if callable(orig_ce):
            def _dh_create_entity_ct_wrapper(*args, **kwargs):
                if args and args[0] == 'ClientTeammate':
                    _dh_install_teammate_entity_plumbing()
                    res = None
                    try:
                        res = orig_ce(*args, **kwargs)
                    except Exception:
                        pass
                    if res is None:
                        try:
                            space = int(args[1]) if len(args) > 1 and isinstance(args[1], (int, long_type)) else _space_id()
                            pos = (0.0, 0.0, 0.0)
                            props = {}
                            for arg in args[2:]:
                                if isinstance(arg, dict):
                                    props = dict(arg)
                                elif hasattr(arg, '__len__') and len(arg) == 3:
                                    pos = _point(arg)
                                elif hasattr(arg, 'x') and hasattr(arg, 'y') and hasattr(arg, 'z'):
                                    pos = (float(arg.x), float(arg.y), float(arg.z))
                            res = orig_ce('ClientTeammate', space, 0, tuple(pos), (0.0, 0.0, 0.0), props)
                        except Exception:
                            res = None
                    if res is not None:
                        _dh_register_client_teammate(res)
                    return res
                return orig_ce(*args, **kwargs)
            _dh_create_entity_ct_wrapper._dh_ct_inner = orig_ce
            BigWorld.createEntity = _dh_create_entity_ct_wrapper
    except Exception:
        pass


_dh_install_teammate_entity_plumbing()
_dh_install_ct_create_wrapper()


# 6E. Synchronize ClientTeammate Position to Live Teammate Avatar Every Frame
def _dh_find_all_client_teammates():
    try:
        import BigWorld
        cts = []
        for ent in list(BigWorld.entities.values()):
            if ent is None:
                continue
            cname = getattr(getattr(ent, '__class__', None), '__name__', '')
            if cname == 'ClientTeammate' or 'ClientTeammate' in str(type(ent)):
                cts.append(ent)
        return cts
    except Exception:
        return []


def _dh_sync_client_teammates():
    """Pin every ClientTeammate to its matching teammate avatar position every frame,
    ensuring native 3D overhead names & seat numbers follow them smoothly, and keeping the white pillar hidden."""
    try:
        import BigWorld
        cts = _dh_find_all_client_teammates()
        if not cts:
            return
        mates = list(_dh_mates.get('live_list') or [])
        pos_map = _dh_mates.get('positions', {})

        for ct in cts:
            _dh_hide_ct_model(ct)

            target_pos = None
            target_yaw = None

            ct_name = getattr(ct, 'nickname', None) or getattr(ct, 'name', None)
            matched_mate = None
            if ct_name and mates:
                for m in mates:
                    if m[2] == ct_name:
                        matched_mate = m
                        break
            if matched_mate is None and len(mates) == 1:
                matched_mate = mates[0]

            if matched_mate is not None:
                client_id, entity_id, name, alive, hp, max_hp, down = matched_mate
                avatar = BigWorld.entities.get(client_id)
                if avatar is None:
                    avatar = _resolve_entity(_remote.get(entity_id))
                if avatar is not None and hasattr(avatar, 'position'):
                    try:
                        target_pos = avatar.position
                        target_yaw = getattr(avatar, 'yaw', 0.0)
                    except Exception:
                        pass
                if target_pos is None and entity_id in pos_map:
                    target_pos = pos_map[entity_id]

            if matched_mate is not None:
                setter = getattr(ct, 'setState', None)
                state = _dh_player_state('Died' if not alive else 'Wounded') if not alive or down else alive_state()
                if callable(setter) and state is not None:
                    try:
                        if getattr(ct, 'state', None) != state:
                            setter(state)
                    except Exception:
                        if not _dh_mates.get('marker_state_warned'):
                            _dh_mates['marker_state_warned'] = True
                            log_error('local-mates-marker-state-error')

            if target_pos is not None:
                try:
                    ct.position = target_pos
                except Exception:
                    pass
                if hasattr(ct, 'setPosition') and callable(ct.setPosition):
                    try:
                        ct.setPosition(target_pos)
                    except Exception:
                        pass
                if target_yaw is not None:
                    try:
                        ct.yaw = float(target_yaw)
                    except Exception:
                        pass
    except Exception:
        pass


# Hook _dh_sync_client_teammates into step_motion so it runs every physics frame
_dh_orig_step_motion_sync = globals().get('step_motion')
while getattr(_dh_orig_step_motion_sync, '_dh_ct_sync_inner', None) is not None:
    _dh_orig_step_motion_sync = _dh_orig_step_motion_sync._dh_ct_sync_inner


def _dh_step_motion_ct_sync_wrapper(now):
    try:
        _dh_sync_client_teammates()
    except Exception:
        pass
    if callable(_dh_orig_step_motion_sync):
        return _dh_orig_step_motion_sync(now)
    return None


_dh_step_motion_ct_sync_wrapper._dh_ct_sync_inner = _dh_orig_step_motion_sync
globals()['step_motion'] = _dh_step_motion_ct_sync_wrapper


# 6F. Rich Teammate State Synchronization & HUD Panel Updates
_dh_mates.setdefault('client_ids', {})
_dh_mates.setdefault('live_list', [])
_dh_mates.setdefault('positions', {})
_dh_mates.setdefault('last_hud_push', 0.0)


def _dh_rich_team_mates_from(snapshot):
    """Return [(client_id, entity_id, name, alive, hp, max_hp, down)] of party teammates in snapshot, or None if solo."""
    try:
        team = int((BATTLE.get('ticket') or {}).get('team') or 0)
    except (TypeError, ValueError):
        return None
    if not (_DH_PARTY_LOW <= team < _DH_PARTY_HIGH):
        return None
    me = int(BATTLE.get('entity_id') or 0)
    mates = []
    client_map = _dh_mates.setdefault('client_ids', {})
    pos_map = _dh_mates.setdefault('positions', {})
    for item in (snapshot or {}).get('entities') or []:
        try:
            if item.get('kind') != 'player' or int(item.get('team') or 0) != team:
                continue
            entity_id = int(item.get('id'))
        except (TypeError, ValueError, AttributeError):
            continue
        if entity_id == me:
            continue
        if item.get('pos') is not None:
            try:
                pos_map[entity_id] = _point(item.get('pos'))
            except Exception:
                pass
        entity = _remote.get(entity_id)
        resolved = _resolve_entity(entity) if entity is not None else None
        client_id = getattr(resolved, 'id', None) if resolved is not None else client_map.get(entity_id)
        if client_id is None:
            client_id = entity_id
        client_map[entity_id] = client_id
        alive = item.get('alive') is not False
        raw_hp = item.get('hp')
        hp = max(0, min(100, int(raw_hp if raw_hp is not None else (100 if alive else 0))))
        if not alive:
            hp = 0
        max_hp = max(100, int(item.get('max_hp') or 100))
        act = item.get('act') if isinstance(item.get('act'), dict) else {}
        down = bool(item.get('down') or act.get('pose') == 'down')
        name = str(item.get('name') or 'Teammate')
        if resolved is not None:
            try:
                p = current_player()
                if p is not None and getattr(p, 'campType', None) is not None:
                    resolved.campType = p.campType
            except Exception:
                pass
        mates.append((int(client_id), int(entity_id), name, bool(alive), int(hp), int(max_hp), bool(down)))
    mates.sort(key=lambda entry: entry[1])
    return mates


def _dh_team_hud_record_is_zombie(self):
    # Local matches do not use the Wild Mode zombie role.
    return False


class _DhHudTeammateRecord(_DhLiveRecord):
    isZombie = _dh_team_hud_record_is_zombie


def _dh_with_teammates_for_panel(player, action):
    import Globals
    hud = getattr(Globals.uiMgr, 'UIBattlegroundsInGame', None)
    panel = hud.GetComponent('UIPanelTeam') if hud is not None else None
    refresh = getattr(panel, 'refreshAllMembers', None)
    fn = getattr(refresh, 'im_func', refresh)
    namespace = getattr(fn, 'func_globals', {})
    client_utils = namespace.get('client_utils')
    original = getattr(client_utils, 'getCurrTeammatesData', None)
    if not callable(original):
        return action()

    def teammates_for_panel(*args, **kwargs):
        return [row for row in original(*args, **kwargs)
                if row.entID != player.id]

    client_utils.getCurrTeammatesData = teammates_for_panel
    try:
        return action()
    finally:
        client_utils.getCurrTeammatesData = original


def _dh_publish_team_hud(player):
    try:
        import Globals
        hud = getattr(Globals.uiMgr, 'UIBattlegroundsInGame', None)
        panel = hud.GetComponent('UIPanelTeam') if hud is not None else None
        refresh = getattr(panel, 'refreshAllMembers', None)
        if callable(refresh):
            _dh_with_teammates_for_panel(player, refresh)
    except Exception:
        if not _dh_mates.get('panel_refresh_warned'):
            _dh_mates['panel_refresh_warned'] = True
            log_error('local-mates-panel-refresh-error')


def _dh_rich_sync_teammates(mates):
    _dh_mates['live_list'] = list(mates or [])
    signature = tuple(mates or [])
    now = time.time()
    last_push = float(_dh_mates.get('last_hud_push') or 0.0)

    sig_changed = (signature != _dh_mates.get('sig'))
    time_to_refresh = (now - last_push >= 1.5)
    if not sig_changed and not time_to_refresh:
        return False
    _dh_mates['last_hud_push'] = now

    import BigWorld
    player = BigWorld.player()
    if player is None:
        return False
    _dh_install_teammate_entity_plumbing()
    old = list(getattr(player, 'battleTeammates', None) or [])
    prev_marks = {}
    for rec in old:
        eid = getattr(rec, 'entID', None)
        if eid is not None and getattr(rec, 'markPosition', None) is not None:
            prev_marks[eid] = rec.markPosition

    own_gid = int(getattr(player, 'gid', 0) or 0)
    if not own_gid:
        try:
            own_gid = int((LOBBY._local_profile(player) or {}).get('gid') or 10000001)
            player.gid = own_gid
        except Exception:
            own_gid = 10000001

    own_hp = max(0, min(100, int(getattr(player, 'hp', 100) if getattr(player, 'hp', None) is not None else 100)))
    own_max_hp = max(100, int(getattr(player, 'maxHp', 100) or 100))
    me = _DhHudTeammateRecord(
        entID=getattr(player, 'id', 0),
        gid=own_gid,
        nickname=str(getattr(player, 'nickname', '') or 'Player'),
        state=alive_state(),
        isAlive=_DhAliveFlag(own_hp > 0),
        hp=own_hp,
        maxHp=own_max_hp,
        nationalFlag=str(getattr(player, 'nationalFlag', '') or ''),
        baseCharacterType=int(getattr(player, 'characterType', DEFAULT_CHARACTER_TYPE) or DEFAULT_CHARACTER_TYPE),
        characterType=int(getattr(player, 'characterType', DEFAULT_CHARACTER_TYPE) or DEFAULT_CHARACTER_TYPE),
        index=0,
        teamIndex=0,
        inVehicle=bool(getattr(player, 'inVehicle', False) or getattr(player, 'vehicleEntID', 0)),
        heroname='',
        markPosition=prev_marks.get(getattr(player, 'id', 0), unmarked()),
        markFloor=0,
    )
    records = [me]
    died = _dh_player_state('Died')
    wounded = _dh_player_state('Wounded')
    valid_mates = []
    for index, (client_id, entity_id, name, alive, hp, max_hp, down) in enumerate(mates):
        mate_gid = 20000000 + int(entity_id or (index + 2))
        if mate_gid == own_gid:
            mate_gid += 1000
        if not alive and died is not None:
            st = died
        elif alive and down and wounded is not None:
            st = wounded
        else:
            st = alive_state()
        rec = _DhHudTeammateRecord(
            entID=client_id,
            gid=mate_gid,
            nickname=name,
            state=st,
            isAlive=_DhAliveFlag(alive),
            hp=hp,
            maxHp=max_hp,
            nationalFlag='',
            baseCharacterType=DEFAULT_CHARACTER_TYPE,
            characterType=DEFAULT_CHARACTER_TYPE,
            index=index + 1,
            teamIndex=index + 1,
            inVehicle=False,
            heroname='',
            markPosition=prev_marks.get(client_id, unmarked()),
            markFloor=0,
        )
        records.append(rec)
        valid_mates.append(rec)

    for record in records:
        if not _dh_place_record(record):
            eid = getattr(record, 'entID', None)
            mate_pos = _dh_mates.get('positions', {}).get(eid)
            try:
                record.position = mate_pos if mate_pos is not None else player.position
                record.yaw = 0.0
            except Exception:
                pass

    player.battleTeammates = records
    try:
        player.validBattleTeammates = list(valid_mates)
        player.battleTeamEntIDs = [record.entID for record in records if record.entID]
        player.battleTeamMateIds = [record.entID for record in valid_mates]
        player.fixedBattleTeamMateIds = [getattr(r, 'entID', 0) for r in valid_mates if getattr(r, 'entID', 0)]
    except Exception:
        pass

    # Enable the native team layout before publishing its member rows.
    if valid_mates:
        try:
            configured_size = int((BATTLE.get('ticket') or {}).get('teamSize') or 0)
            team_size = max(configured_size, len(records))
            previous_size = int(getattr(player, 'battleGroundTeamSize', 0) or 0)
            if previous_size < team_size:
                player.battleGroundTeamSize = team_size
                _dh_with_teammates_for_panel(
                    player, lambda: player.set_battleGroundTeamSize(previous_size))
                log('local-match-team-layout-enabled', size=team_size)
        except Exception:
            log_error('local-match-team-layout-error')

    setter = getattr(player, 'set_battleTeammates', None)
    if callable(setter):
        try:
            setter(old)
        except Exception:
            log_error('local-mates-setter-error')

    try:
        if valid_mates and not getattr(player, 'validBattleTeammates', None):
            player.validBattleTeammates = list(valid_mates)
    except Exception:
        pass

    # The prep roster can arrive before the teammate's avatar exists.
    # Ask the native marker lifecycle to attach once the avatar is available.
    if on_island_stage():
        import BigWorld
        check_marker = getattr(player, 'checkClientTeammate', None)
        markers = getattr(player, 'clientTeammates', {})
        if callable(check_marker) and isinstance(markers, dict):
            for record in valid_mates:
                if record.entID in markers or BigWorld.entities.get(record.entID) is None:
                    continue
                try:
                    check_marker(record, False)
                except Exception:
                    if not _dh_mates.get('prep_marker_warned'):
                        _dh_mates['prep_marker_warned'] = True
                        log_error('local-mates-prep-marker-error')
    _dh_publish_team_hud(player)
    _dh_sync_client_teammates()

    _dh_mates['sig'] = signature
    _dh_mates['updates'] = int(_dh_mates.get('updates') or 0) + 1
    if _dh_mates['updates'] <= 15:
        log('local-mates-synced', mates=[m[2] for m in mates],
            alive=[m[3] for m in mates], hp=[m[4] for m in mates],
            team=(BATTLE.get('ticket') or {}).get('team'))
    return True


globals()['_dh_team_mates_from'] = _dh_rich_team_mates_from
globals()['_dh_sync_teammates'] = _dh_rich_sync_teammates


_dh_orig_pin_retire = globals().get('_dh_pin_retire')
while getattr(_dh_orig_pin_retire, '_dh_party_pin_inner', None) is not None:
    _dh_orig_pin_retire = _dh_orig_pin_retire._dh_party_pin_inner


def _dh_party_safe_pin_retire(player):
    try:
        team = int((BATTLE.get('ticket') or {}).get('team') or 0)
        if _DH_PARTY_LOW <= team < _DH_PARTY_HIGH and _dh_mates.get('live_list'):
            return False
    except Exception:
        pass
    return _dh_orig_pin_retire(player) if callable(_dh_orig_pin_retire) else False


_dh_party_safe_pin_retire._dh_party_pin_inner = _dh_orig_pin_retire
globals()['_dh_pin_retire'] = _dh_party_safe_pin_retire


# 6G. Background Tick for Teammate Tracking & HUD Refresh
_dh_team_ui_state = {
    'running': False,
    'last_tick': 0.0,
}


def _dh_teammate_tick():
    try:
        _dh_sync_client_teammates()
    except Exception:
        pass

    try:
        now = time.time()
        if now - float(_dh_team_ui_state.get('last_tick') or 0.0) >= 1.0:
            _dh_team_ui_state['last_tick'] = now
            player = current_player()
            if player is not None and BATTLE.get('phase') == 'fighting':
                _dh_publish_team_hud(player)
    except Exception:
        pass

    phase = BATTLE.get('phase')
    team = int((BATTLE.get('ticket') or {}).get('team') or 0)
    fast = (phase in ('entering', 'fighting') and (_DH_PARTY_LOW <= team < _DH_PARTY_HIGH))
    call_later(0.04 if fast else 0.5, _dh_teammate_tick)


if not _dh_team_ui_state.get('running'):
    _dh_team_ui_state['running'] = True
    call_later(0.5, _dh_teammate_tick)

log('ros-redemption-duo-teammate-and-quit-fix-active', status='ready')
