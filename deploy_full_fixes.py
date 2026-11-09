import zlib
import base64
import hashlib
import os

print("=== BUILDING FULL MASTER PATCH (BOTS, VEHICLES, BIKE, TANGO, KILLFEED) ===")

# 1. Read base clean_remote_battle.py
with open(r'c:\Users\seanj\dev\clean_remote_battle.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Strip any previous appended patch blocks
marker = '# =============================================================================='
if marker in code:
    code = code[:code.find(marker)].rstrip() + '\n\n'

patch_code = '''# ==============================================================================
# ROS REDEMPTION - MASTER ENGINE PATCH
# 1. Non-hero map UISelectHero suppression
# 2. Resilient matchmaking & zero step 0 failures
# 3. Vehicle Spawning: Boats in water, Land vehicles on land
# 4. Killfeed color fix: Real killer ID for BLUE name & bot kill crediting
# 5. Shift+1 Bicycle & In-game Tango Emote handlers
# ==============================================================================

# 1. Guard UISelectHero
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
        if _orig_eui and not getattr(_orig_eui, '_redemption_guard', False):
            def _safe_enter_ui(name, *args, **kwargs):
                if name == 'UISelectHero':
                    cur_map = BATTLE.get('map') or (BATTLE.get('ticket') or {}).get('map', 0)
                    if cur_map not in (730, 731, 732, 733):
                        return None
                return _orig_eui(name, *args, **kwargs)
            _safe_enter_ui._redemption_guard = True
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
            # Detect water spots (Type 2 or depth below sea level < -1000)
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

# 4. Killfeed color fix: Blue name on player kills & bot kill credit
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

        # Check if current player is the killer
        is_my_kill = (killer_name == getattr(player, 'name', '') or
                      (my_id is not None and killer_id == my_id) or
                      (my_bid is not None and killer_id == my_bid))

        actual_killer_id = my_id if (is_my_kill and my_id is not None) else killer_id
        show_kill_feed(killer_name, weapon_name, target_name, actual_killer_id, victim_id)

        # Credit kill if killed by player (both bots and players!)
        if is_my_kill and not on_island_stage() and target is not None:
            credit_player_kill(target, item)

        call_later(BODY_LINGER, bury_body, battle_id)
        log('local-battle-remote-kill', target=battle_id, killer=killer_name, weapon=weapon_name)
        return True

    globals()['remote_died'] = redemption_remote_died
    log('ros-redemption-fix', fix='killfeed blue name & kill counter installed')
except Exception:
    pass

# 5. Shift+1 Bicycle & In-Game Tango / Emote RPC handlers
try:
    def redemption_use_portable_vehicle(player, *args, **kwargs):
        try:
            x, y, z = _point(player.position)
            yaw = float(getattr(player, 'yaw', 0.0) or 0.0)
            cx, cz = x + 2.5 * math.sin(yaw), z + 2.5 * math.cos(yaw)
            ground = ground_height(cx, cz) or y
            # 140073 is Summer Bicycle
            bike_id = spawn_vehicle('LandCar', 140073, 140073, cx, cz, ground, yaw)
            if bike_id is not None:
                get_on(player, bike_id, True)
                log('local-bicycle-summoned', bike=bike_id)
                return True
        except Exception:
            pass
        return False

    def redemption_play_action(player, action_id=0, *args, **kwargs):
        try:
            if hasattr(player, 'playAnimation'):
                player.playAnimation(str(action_id))
            elif hasattr(player, 'onPlayAction'):
                player.onPlayAction(int(action_id))
            log('local-play-action', action=action_id)
        except Exception:
            pass
        return None

    _h = globals().get('_handlers') or globals().get('handlers')
    if isinstance(_h, dict):
        _h['reqPlayAction'] = redemption_play_action
        _h['playAction'] = redemption_play_action
        _h['reqPlayEmoji'] = redemption_play_action
        _h['playEmoji'] = redemption_play_action
        _h['reqSummonPortableVehicle'] = redemption_use_portable_vehicle
    log('ros-redemption-fix', fix='bicycle summon & tango action handlers installed')
except Exception:
    pass

log('ros-redemption-master-patch-active', status='ready')
'''

new_code = code + '\n\n' + patch_code

# Validate compile
compile(new_code, 'clean_remote_battle', 'exec')
print('clean_remote_battle compiled successfully! (length: %d)' % len(new_code))

with open(r'c:\Users\seanj\dev\clean_remote_battle.py', 'w', encoding='utf-8') as f:
    f.write(new_code)

# 2. Encrypt with keystream cipher (Key A29631E24BA664471E72043DE2CB8BCBF85DE0000A1FCB5A345EC289B10B9287)
key_hex = 'a29631e24ba664471e72043de2cb8bcbf85de0000a1fcb5a345ec289b10b9287'
K = bytes.fromhex(key_hex)
compressed = zlib.compress(new_code.encode('utf-8'), 9)
parts = []
i = 0
c = 0
size = len(compressed)
while i < size:
    chunk = compressed[i:i + 65536]
    blocks = (len(chunk) + 31) // 32
    ks = b''.join([hashlib.sha256(K + str(c + k).encode('ascii')).digest() for k in range(blocks)])[:len(chunk)]
    c += blocks
    parts.append(bytes([x ^ y for x, y in zip(chunk, ks)]))
    i += 65536

encrypted = b''.join(parts)
b64_str = base64.b64encode(encrypted).decode('ascii')
b_lines = ['    "%s",\n' % b64_str[j:j+80] for j in range(0, len(b64_str)-80, 80)]
rem = b64_str[len(b64_str)-(len(b64_str)%80):]
if rem:
    b_lines.append('    "%s",\n' % rem)
b_payload = '_B = [\n' + ''.join(b_lines) + ']\n\n'

# Read original remote-battle.py template
with open(r'C:\DieHardROS\local_update\hot\remote-battle.py', 'r', encoding='utf-8') as f:
    orig_template = f.read()

s = orig_template.find('_B = [')
e = orig_template.find(']\n\n', s)
if s >= 0 and e >= 0:
    new_remote = orig_template[:s] + b_payload + orig_template[e+3:]
else:
    raise ValueError('Could not find _B array in remote-battle.py!')

new_sha = hashlib.sha256(new_remote.encode('utf-8')).hexdigest()

# Targets: Update remote-battle.py AND hot-battle-*.py!
targets = [
    r'C:\DieHardROS\local_update\hot\remote-battle.py',
    r'C:\DieHardROS\runtime\app\local_update\hot\remote-battle.py',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\hot-battle-2026.11.02m50.py',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app\local_update\hot\remote-battle.py',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\local_update\hot\remote-battle.py'
]

for t in targets:
    if os.path.exists(t):
        with open(t, 'w', encoding='utf-8') as f:
            f.write(new_remote)
        sha_path = t + '.sha256'
        try:
            with open(sha_path, 'w', encoding='utf-8') as f:
                f.write(new_sha)
        except Exception:
            pass
        print('Successfully updated target:', t)

print('New remote-battle.py sha256:', new_sha)
print('>>> ALL 5 MASTER FIXES COMPILED, ENCRYPTED, & INSTALLED ACROSS RUNTIME! <<<')

