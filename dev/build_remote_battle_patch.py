import zlib
import base64
import hashlib
import os

print("=== BUILDING & ENCRYPTING MASTER BATTLE PATCH ===")

# Read current clean_remote_battle.py
with open(r'c:\Users\seanj\dev\clean_remote_battle.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Check if already appended
marker = '# ROS REDEMPTION - BATTLE & BOT MATCH ENTRY FIXES'
if marker in code:
    code = code[:code.find(marker)].rstrip() + '\n\n'

patch_code = '''# ==============================================================================
# ROS REDEMPTION - BATTLE & BOT MATCH ENTRY FIXES
# ==============================================================================

# 1. Patch UISelectHero exception guard
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
                    log('ros-redemption-fix', fix='UISelectHero._showHeroList guarded')
except Exception:
    pass

# 2. Patch Globals.uiMgr.enter_ui to suppress UISelectHero on non-hero maps
try:
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
            log('ros-redemption-fix', fix='UISelectHero suppressed on non-hero maps')
except Exception:
    pass

# 3. Fast matchmaking timer
try:
    def redemption_matching_tick(player):
        if BATTLE.get('phase') != 'matching':
            return
        for packet in drain():
            if isinstance(packet, dict) and 'queued' in packet:
                BATTLE['queue'] = packet
        queue = BATTLE.get('queue')
        elapsed = time.time() - BATTLE.get('matching_started', 0.0)

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
    log('ros-redemption-fix', fix='fast matchmaking installed')
except Exception:
    pass

# 4. Patch enter_battle to avoid calling PRE_ENTERING on Ghillie Island
try:
    _orig_eb = globals().get('enter_battle')
    def redemption_enter_battle(player):
        if BATTLE['phase'] == 'entering':
            return False
        BATTLE.update(phase='entering', step=0, step_started=time.time())
        ticket_map = (BATTLE.get('ticket') or {}).get('map', 0)
        if ticket_map in (730, 731, 732, 733):
            _match_state(player, 'PRE_ENTERING')
        else:
            try:
                import Globals as _g
                if hasattr(_g, 'uiMgr'):
                    _g.uiMgr.leave_ui('UISelectHero')
            except Exception:
                pass
        log('local-battle-entering', map=ticket_map)
        run_steps(player)
        return True

    globals()['enter_battle'] = redemption_enter_battle
    log('ros-redemption-fix', fix='safe enter_battle installed')
except Exception:
    pass

# 5. Patch step_join with resilient join handler (Zero step 0 failures)
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
            'gid': int(profile.get('gid') or 10000001),
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
    log('ros-redemption-fix', fix='resilient step_join installed')
except Exception:
    pass

log('ros-redemption-master-patch-active', status='ready')
'''

new_code = code + '\n\n' + patch_code

# Test compile
compile(new_code, 'clean_remote_battle', 'exec')
print('clean_remote_battle compiled successfully!')

# Write clean_remote_battle.py
with open(r'c:\Users\seanj\dev\clean_remote_battle.py', 'w', encoding='utf-8') as f:
    f.write(new_code)
print('clean_remote_battle.py written (size:', len(new_code), ')')

# Encrypt for remote-battle.py
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

# Compute sha256
new_sha = hashlib.sha256(new_remote.encode('utf-8')).hexdigest()

# Write to all targets
targets = [
    r'C:\DieHardROS\local_update\hot\remote-battle.py',
    r'C:\DieHardROS\runtime\app\local_update\hot\remote-battle.py'
]

for t in targets:
    if os.path.exists(t):
        with open(t, 'w', encoding='utf-8') as f:
            f.write(new_remote)
        sha_path = t + '.sha256'
        with open(sha_path, 'w', encoding='utf-8') as f:
            f.write(new_sha)
        print('Updated target:', t)

print('New remote-battle.py sha256:', new_sha)
print('>>> ALL BATTLE ENTRY FIXES ENCRYPTED & INSTALLED SUCCESSFULLY! <<<')

