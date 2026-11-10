# -*- coding: utf-8 -*-
import os

patch_code = '''

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
'''

with open('clean_remote_battle.py', 'r', encoding='utf-8') as f:
    orig = f.read()

marker = '# ROS REDEMPTION - KILLFEED COLOR ENHANCEMENTS'
if marker in orig:
    orig = orig[:orig.find(marker)].rstrip()

new_content = orig + '\n' + patch_code

compile(new_content, 'clean_remote_battle', 'exec')
print("Compiled clean_remote_battle successfully!")

with open('clean_remote_battle.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
print("Updated clean_remote_battle.py (size: %d bytes)" % len(new_content))

# Also copy to dev\\clean_remote_battle.py
try:
    with open(r'dev\clean_remote_battle.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Updated dev/clean_remote_battle.py")
except Exception:
    pass

print("=== READY TO REBUILD REMOTE BATTLE PATCH ===")
