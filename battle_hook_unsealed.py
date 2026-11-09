# -*- coding: utf-8 -*-
"""DieHard ROS battle hook -- START, the battleground and replication.

Runs INSIDE ros64.exe next to client/lobby_hook.py, as the module
``ros_local_battle``; the lobby hook calls ``attach()`` once and hands over
every battle ticket the backend sends.  Keep the syntax valid for Python 2.7
and 3 (it is syntax-checked and unit-tested outside the game).

What the game does online
    UIModes._doMatch          -> player.base.getReadyForBattleGround()
    server                    -> player.syncMatchState / syncMatchingProgress
    server                    -> player.transferToBattleServer(ip, port, ...)
    client                    -> BigWorld.logOn(battle host) -> Avatar in a space

What happens here
    getReadyForBattleGround   -> backend_server/battle_rpc.py answers with a
                                 ticket: the local battle host's address
    matching screen           -> played from the ticket (syncMatchState +
                                 syncMatchingProgress on the player)
    battle entry              -> ENTER_STEPS below: join the battle host, load
                                 the map, make the player, enter the space
    replication               -> a timer sends our position to the battle host
                                 and draws the snapshot it answers with
                                 (backend_server/battle_server.py)

The engine calls the entry needs are not all known yet, so every step is
named, tried in order and logged: the JSONL log says exactly which step a run
stopped on, and which engine call worked (``local-battle-step``).
"""

import json
import math
import re
import socket
import sys
import time
import uuid

try:
    long_type = long  # noqa: F821 (Python 2)
except NameError:
    long_type = int
# Names that are almost certainly calls, not fields (see _space_default).
METHOD_NAME = re.compile(r'^(get|set|on|req|request|query|sync|send|do|refresh|update|try|'
                         r'check|add|del|remove|open|close|init|reset|clear|notify|show|'
                         r'hide|play|stop|start|create|destroy|load|release)[A-Z_]')
# Names that read as an empty list rather than 0.
PLURAL_NAME = re.compile(r'(?:[a-z]s|IDs|Ids|List|Array)$')

JOIN_PREFIX = 'ROS_BATTLE_JOIN_V1 '
INPUT_PREFIX = 'ROS_BATTLE_INPUT_V1 '
KILL_PREFIX = 'ROS_BATTLE_KILL_V1 '
BOT_PREFIX = 'ROS_BATTLE_BOT_V1 '
LEAVE_PREFIX = 'ROS_BATTLE_LEAVE_V1 '
PING_PREFIX = 'ROS_BATTLE_PING_V1 '
QUEUE_PREFIX = 'ROS_BATTLE_QUEUE_V1 '
QUEUE_SILENT = 4.0                      # s without a queue answer: an older battle host - the old timer
LOOT_PREFIX = 'ROS_BATTLE_LOOT_V1 '
PING_INTERVAL = 1.0
PUMP_DELAY = 0.01
LATENCY_SMOOTHING = 0.3
LATENCY_LOG_INTERVAL = 30.0

# How often we tell the battle host where we are (and get the world back).
SEND_RATE = 20.0
# The matching screen's progress bar: how many "players" it counts up to.
MATCH_TARGET = 100
MATCHING_TICK = 0.5
# An entry step that answers 'wait' is retried this often, for this long.
STEP_RETRY = 0.2
STEP_TIMEOUT = 60.0
# Loading a real map off disk is allowed to take much longer than a step that
# only calls into the client.
STEP_TIMEOUTS = {'wait-scene': 300.0, 'stream-terrain': 300.0, 'wait-world': 300.0,
                 'player-entity': 15.0}
# Spawn height used until the ground's own is known (step_ground): high enough
# to be above any terrain, so the stream happens around the right x/z.
PROVISIONAL_HEIGHT = 500.0
# A body is placed this far above the ground it stands on.
STAND_HEIGHT = 1.0
# How long step_ground waits for the landscape to answer for the spawn.
GROUND_WAIT = 5.0
# How often the wait says where the load has got to.
LOADING_REPORT = 2.0
# The client flags that describe a map load, for that report.
LOADING_FLAGS = ('inLoading', 'inLoadingStage1', 'inLoadingStage2', 'MAP_ID',
                 'fightUILoaded', 'firstEnterMap', 'hallSceneReady')
# Classes tried, in order, for a replicated other player.  The first one the
# engine accepts is remembered.
# BattleGroundAvatar first: it is what other players are online and what
# the replay system builds them as.  ClientTeammate is only the white
# stand-in pillar the client shows for a teammate out of view.
REMOTE_CLASSES = ('BattleGroundAvatar', 'ClientTeammate')
# The same, for our own body in the battleground.  BattleGroundAvatar is what
# the game's own client-side battle entry builds (annal/AnnalPlayer.py,
# createPlayer) - the replay system plays a whole match with no server, which
# is the same problem this hook has.
PLAYER_CLASSES = ('BattleGroundAvatar', 'Avatar', 'Athlete')
# The battleground's own entity (Globals.spaceEntity), tried in this order.
SPACE_CLASSES = ('BattleGroundSpace', 'BattleGroundRos2Space')
# Hall screens closed before the map loads (see step_leave_lobby).
LOBBY_SCREENS = ('UIMain', 'UISelectCharacter')
# Object.DestroyImmediate reads this off what it is handed (see lobby_hook).
DESTROYED_FLAG = '____destroyed__'
# AnnalPlayer.createPlayer's own default when a character type is not known.
DEFAULT_CHARACTER_TYPE = 10002

# The lobby hook module (ros_local_lobby); set by attach().
LOBBY = None
# Everything about the battle we are in or joining.
BATTLE = {
    'phase': 'idle',        # idle | matching | entering | fighting
    'ticket': None,         # what the backend answered START with
    'address': None,        # (host, port) of the battle host
    'socket': None,
    'entity_id': 0,         # our id in the battle host's world
    'match': None,          # map, spawn, tick rate...
    'step': 0,              # index into ENTER_STEPS
    'step_started': 0.0,
    'matching_started': 0.0,
    'seq': 0,
    'tick': 0,
    'map': 0,               # the map being loaded, and where that id came from
    'map_from': '',
    'spawn': None,          # the map's own birth position, when the client knows it
    'space': 0,
    'player': None,         # the entity we made for ourselves
    'space_entity': None,   # the battleground entity (Globals.spaceEntity)
    'remote_class': None,   # the class the engine accepted for other players
    'create_with': None,    # the createEntity argument list this build wants
    'proxy_with': None,     # how setProxy took our entity
    'place_with': None,     # how a replicated entity is moved
    'position_with': {},    # method name -> the position type that method takes
    'map_requested': False,  # our own map load has been asked for (guard_map_reload)
    'streaming': False,     # the pre-entry terrain stream was asked for
    'streamed': False,      # ...and its callback came back
    'markers': {},          # marker field -> last (x, z) logged (watch_marker)
    'marker_fields': None,  # the player's marker-like field names, found once
    'reported_at': 0.0,     # last time the map load was reported
    'inbox': [],
    'ping_seq': 0,
    'ping_at': 0.0,
    'rtt': None,
    'rtt_logged_at': 0.0,
    'pumping': False,
}
# battle entity id -> whatever the engine gave us back for it
_remote = {}
_logged_once = set()





def lobby_appearance():
    """The appearance the lobby saved (lobby_hook.stored_appearance)."""
    function = getattr(LOBBY, 'stored_appearance', None)
    try:
        stored = function() if callable(function) else {}
    except Exception:
        stored = {}
    return stored if isinstance(stored, dict) else {}


_gun_props = {}


def gun_prop_for(gun_id):
    """The battleground prop of a gun (PROP_TYPE.ITEM_INDEX is the gun id,
    the reverse of iBattleGround.curWeaponAppearance)."""
    if not _gun_props:
        module = _properties_module()
        try:
            for key, data in module.iterBattleGroundPropData():
                kind = getattr(data, 'PROP_TYPE', None)
                index = getattr(kind, 'ITEM_INDEX', None)
                name = type(kind).__name__
                if index and 'Gun' in name and 'Component' not in name and int(index) not in _gun_props:
                    _gun_props[int(index)] = int(key)
        except Exception:
            log_error('local-battle-gun-props-error')
    return _gun_props.get(int(gun_id or 0))


def lobby_gun_prop():
    """The firearm shown with you in the lobby (Depot > Firearms "show in
    lobby": dtsOutGameWeapon, a weapon skin) as the island's gun.  Its skin
    shows through gunID2AppearanceIDDict."""
    appearance = int(lobby_appearance().get('dtsOutGameWeapon') or 0)
    if not appearance:
        return None
    try:
        gun_id = int(__import__('dts_appearance_utils').getDtsWeaponAppearanceGunID(appearance) or 0)
    except Exception:
        return None
    return gun_prop_for(gun_id)


def gun_bullet(gun):
    module = sys.modules.get('dts_utils')
    getter = getattr(module, 'getDtsGunBullet', None) if module is not None else None
    if not callable(getter):
        return 0
    try:
        return int(getter(gun) or 0)
    except Exception:
        return 0


def add_item(player, item, number):
    BATTLE['item_serial'] = BATTLE.get('item_serial', 0) + 1
    uuid_text = 'rl-%d-%d' % (item, BATTLE['item_serial'])
    try:
        player.onAddDtsItem(item, [{'uuid': uuid_text, 'number': number, 'info': {}}], 0, number)
        return True
    except Exception:
        log_error('local-battle-item-error', item=item, number=number)
        return False


def switch_weapon(player, slot):
    try:
        player.dtsCurWeapon = slot
        player.onChangeDtsWeapon()
        return True
    except Exception:
        log_error('local-battle-switch-error', slot=slot)
        return False


def on_change_weapon(player, slot=0, *_args, **_kwargs):
    try:
        slot = int(slot)
    except Exception:
        return None
    call_later(WEAPON_SWITCH_DELAY, switch_and_attach, player, slot)
    return None


def switch_and_attach(player, slot):
    if slot == BOMB_SLOT and getattr(player, 'dtsCurWeapon', None) == BOMB_SLOT:
        cycle_bomb(player)
        return True
    if not slot_holds_weapon(player, slot):
        debug('local-battle-switch-refused', slot=slot)
        switch_weapon(player, getattr(player, 'dtsCurWeapon', MELEE_SLOT))
        return False
    switch_weapon(player, slot)
    if slot in GUN_SLOTS + (PISTOL_SLOT,):
        auto_attach(player, slot)
    return True


def slot_holds_weapon(player, slot):
    if slot == MELEE_SLOT:
        return True
    try:
        value = getattr(player, 'dtsWeapon%d' % slot)
    except Exception:
        return False
    try:
        if hasattr(value, 'keys'):
            return bool(int(value['weaponID'] or 0))
        return bool(int(value or 0))
    except Exception:
        return False


def current_gun(player):
    try:
        bag = player.gameObject.GetComponent('WeaponBag')
        return bag.getWeapon(int(player.dtsCurWeapon))
    except Exception:
        return None


def reload_seconds(magazine):
    rail = getattr(magazine, 'railData', None)
    for name in ('RELOAD_TIME', 'reloadTime', 'RELOAD_DURATION'):
        value = getattr(rail, name, None) if rail is not None else None
        try:
            if value:
                return float(value)
        except Exception:
            continue
    return DEFAULT_RELOAD_SECONDS


def on_reload(player, *_args, **_kwargs):
    gun = current_gun(player)
    getter = getattr(gun, 'getCurMagazine', None) if gun is not None else None
    if not callable(getter):
        return None
    try:
        magazine = getter()
        need = int(magazine.magazine_capacity) - int(magazine.bullet_count)
        bullet = gun_bullet(int(getattr(magazine, '_dtsItemID', 0) or getattr(gun, '_dtsItemID', 0)))
        have = int(player.getDtsItemCnt(bullet)) if bullet else 0
    except Exception:
        log_error('local-battle-reload-error')
        return None
    slot = getattr(player, 'dtsCurWeapon', None)
    if _reloading.get(slot, 0.0) > time.time():
        return None
    seconds = reload_seconds(magazine)
    _reloading[slot] = time.time() + seconds
    call_later(seconds, finish_gun_reload, player, slot, magazine, bullet, max(0, min(need, have)))
    return None


_reloading = {}


def finish_gun_reload(player, slot, magazine, bullet, count):
    _reloading.pop(slot, None)
    try:
        need = int(magazine.magazine_capacity) - int(magazine.bullet_count)
        count = min(count, need, int(player.getDtsItemCnt(bullet)))
    except Exception:
        pass
    return finish_reload(player, bullet, max(0, count))


def finish_reload(player, bullet, count):
    try:
        player.onReloadDtsWeaponBullet(bullet, count)
        if count > 0:
            player.onDelDtsFoldedItem(bullet, count)
    except Exception:
        log_error('local-battle-reload-finish-error', bullet=bullet, count=count)
        return False
    debug('local-battle-reload', bullet=bullet, count=count)
    return True


LOOT_GUNS = (1001, 1002, 1003, 1006, 1008, 1009, 1011, 1012, 1013, 1014, 1015, 1017, 1021, 1023, 1024,
             1025, 1026, 1036)
LOOT_PISTOLS = (1014, 1015)
PISTOL_PROPS = LOOT_PISTOLS + (90050,)
LOOT_SINGLES = ((1271, 1), (1272, 1), (1273, 1), (1274, 1), (1275, 1), (1201, 1), (1211, 1), (1221, 1),
                (1241, 1), (1242, 1), (1251, 1), (1252, 1), (1253, 1), (1262, 1), (1279, 1), (1302, 1),
                (1303, 1), (1304, 1), (1305, 1), (1401, 2), (1402, 1), (1403, 1), (1404, 1),
                (1, 1), (2, 1), (3, 1), (5, 1), (6, 1), (7, 1), (8, 1), (9, 1), (10, 1),
                (101, 5), (102, 1), (103, 1), (105, 2), (108, 1), (90050, 1), (90051, 3))
LOOT_GUN_COUNT = 14
LOOT_ITEM_COUNT = 28
LOOT_RADIUS = 70.0
LOOT_MIN_RADIUS = 6.0
LOOT_AMMO_OFFSET = 0.8
LOOT_AMMO_STACK = 60
LOOT_LIFT = 0.15
LOOT_SPAWN_BATCH = 6
LOOT_SPAWN_DELAY = 0.2
LOOT_DROP_DISTANCE = 1.2
GUN_SLOTS = (0, 1)
PISTOL_SLOT = 2
MELEE_SLOT = 3
BOMB_SLOT = 4
UNARMED = 1301
QUOTES = '"' + "'"
_loot = {}


def prop_kind(prop):
    module = _properties_module()
    try:
        return type(module.getBattleGroundPropData(int(prop)).PROP_TYPE).__name__
    except Exception:
        return ''


def install_loot_cell():
    module = sys.modules.get('DtsProp')
    if module is None:
        try:
            module = __import__('DtsProp')
        except Exception:
            return False
    cls = getattr(module, 'DtsProp', None)
    if not isinstance(cls, type) or cls.__dict__.get('_rl_loot_cell'):
        return False
    original = cls.__getattribute__

    def loot_getattribute(self, name):
        if name == 'cell':
            try:
                entity_id = original(self, 'id')
            except Exception:
                entity_id = None
            if entity_id in _loot:
                return LootCell(self)
        return original(self, name)

    try:
        cls.__getattribute__ = loot_getattribute
        cls._rl_loot_cell = True
    except Exception:
        log_error('local-battle-loot-cell-error')
        return False
    return True


class LootCell(object):
    def __init__(self, entity):
        self.entity = entity

    def tryPickUp(self, *args):
        call_later(POSE_ECHO_DELAY, pick_up, self.entity, args)

    def tryPickUpForTeammate(self, *args):
        call_later(POSE_ECHO_DELAY, pick_up, self.entity, args)

    def __getattr__(self, name):
        if name == DESTROYED_FLAG:
            return True
        if name.startswith('__'):
            raise AttributeError(name)
        return ignore_call


def spawn_loot(prop, amount, x, z, y=None):
    try:
        import BigWorld
    except Exception:
        return None
    if y is None:
        ground = ground_height(x, z)
        y = ground if ground else (BATTLE['spawn'] or (0.0, 0.0, 0.0))[1]
    space = BATTLE['space'] or getattr(current_player(), 'spaceID', 0)
    install_loot_cell()
    try:
        made = BigWorld.createEntity('DtsProp', space, 0, (x, y + LOOT_LIFT, z), (0.0, 0.0, 0.0),
                                     {'propID': int(prop), 'amount': int(amount), 'info': {}})
    except Exception:
        if once('loot-create'):
            log_error('local-battle-loot-create-error', prop=prop)
        return None
    entity_id = getattr(made, 'id', made)
    _loot[entity_id] = {'prop': int(prop), 'amount': int(amount)}
    return entity_id


def loot_plan(centre, randomizer):
    cx, cz = centre
    plan = []

    def spot():
        angle = randomizer.uniform(0.0, 2.0 * math.pi)
        distance = randomizer.uniform(LOOT_MIN_RADIUS, LOOT_RADIUS)
        return cx + distance * math.sin(angle), cz + distance * math.cos(angle)

    for _index in range(LOOT_GUN_COUNT):
        gun = randomizer.choice(LOOT_GUNS)
        x, z = spot()
        plan.append((gun, 1, x, z))
        bullet = gun_bullet(gun)
        if bullet:
            plan.append((bullet, LOOT_AMMO_STACK, x + LOOT_AMMO_OFFSET, z + LOOT_AMMO_OFFSET))
    for _index in range(LOOT_ITEM_COUNT):
        prop, amount = randomizer.choice(LOOT_SINGLES)
        x, z = spot()
        plan.append((prop, amount, x, z))
    return plan


def scatter_loot(plan=None, index=0):
    if BATTLE['phase'] != 'fighting':
        return 0
    if plan is None:
        import random
        spawn = BATTLE['spawn'] or (0.0, 0.0, 0.0)
        plan = loot_plan((spawn[0], spawn[2]), random.Random(match_uuid()))
    for prop, amount, x, z in plan[index:index + LOOT_SPAWN_BATCH]:
        spawn_loot(prop, amount, x, z)
    index += LOOT_SPAWN_BATCH
    if index < len(plan):
        call_later(LOOT_SPAWN_DELAY, scatter_loot, plan, index)
    else:
        log('local-battle-loot', items=len(_loot), planned=len(plan))
    return index


def remove_loot(entity_id):
    _loot.pop(entity_id, None)
    try:
        import BigWorld
        BigWorld.destroyEntity(entity_id)
    except Exception:
        pass


def requested_amount(args, available):
    for value in args:
        if isinstance(value, bool) or not isinstance(value, (int, long_type)):
            continue
        if 0 < value <= available:
            return int(value)
    return available


COMP_FIELDS = ('muzzle', 'barrel', 'magazine', 'gunStock', 'telescope')
COMP_KINDS = ('PropTypeGunComponentAim', 'PropTypeGunComponentNumeric')


def prop_type(prop):
    module = _properties_module()
    try:
        return module.getBattleGroundPropData(int(prop)).PROP_TYPE
    except Exception:
        return None


def weapon_bag(player):
    try:
        return player.gameObject.GetComponent('WeaponBag')
    except Exception:
        return None


def fill_magazine(player, slot):
    bag = weapon_bag(player)
    try:
        gun = bag.getWeapon(slot)
        magazine = gun.getCurMagazine()
        missing = int(magazine.magazine_capacity) - int(magazine.bullet_count)
        bullet = gun_bullet(int(getattr(magazine, '_dtsItemID', 0) or getattr(gun, '_dtsItemID', 0)))
    except Exception:
        return 0
    if missing <= 0 or not bullet:
        return 0
    try:
        bag.supplyWeaponMagazine(slot, bullet, missing)
    except Exception:
        log_error('local-battle-magazine-error', slot=slot)
        return 0
    return missing


def bag_items(player):
    try:
        return dict(player.dtsItemPackage.itemList)
    except Exception:
        return {}


def comp_fits(comp, gun):
    kind = prop_type(comp)
    if kind is None or type(kind).__name__ not in COMP_KINDS:
        return None
    try:
        field = COMP_FIELDS[int(kind.SLOT_TYPE)]
    except Exception:
        return None
    if int(gun) not in list(getattr(kind, 'GUN_LIST', None) or ()):
        return None
    return field, int(getattr(kind, 'PRIORITY', 0) or 0)


ATTACH_TIP = '%s attached to %s'
WEAPON_BAG_COMP = 'BattlegroundsWeaponBagComp'


def prop_name(prop):
    module = _properties_module()
    try:
        return str(module.getBattleGroundPropData(int(prop)).NAME)
    except Exception:
        return str(prop)


def show_attach_tip(slot, comps, gun):
    try:
        import Globals
        ui = Globals.uiMgr.UIBattlegroundsInGame
        bag = ui.GetComponent(WEAPON_BAG_COMP) if ui is not None else None
        if bag is not None:
            bag.playComponentAutoInsertedAnimation(slot)
    except Exception:
        if once('attach-animation'):
            log_error('local-battle-attach-animation-error')
    text = ', '.join(prop_name(comp) for comp in comps)
    try:
        import Globals
        Globals.uiMgr.systemJumpTip(ATTACH_TIP % (text, prop_name(gun)))
    except Exception:
        if once('attach-tip'):
            log_error('local-battle-attach-tip-error')


def on_sync_operate(player, rail=0, mode=0, *_args, **_kwargs):
    try:
        rail, mode = int(rail), int(mode)
    except Exception:
        return None
    if rail <= 0:
        return None
    call_later(WEAPON_SWITCH_DELAY, apply_operate, player, rail, mode)
    return None


def apply_operate(player, rail, mode):
    try:
        current = player.dtsWeaponOperateTypes
        old = dict(current or {})
    except Exception:
        old = {}
    if old.get(rail) == mode:
        return False
    updated = dict(old)
    updated[rail] = mode
    try:
        player.dtsWeaponOperateTypes = updated
    except Exception:
        log_error('local-battle-operate-error', rail=rail, mode=mode)
        return False
    changed = getattr(player, 'set_dtsWeaponOperateTypes', None)
    if callable(changed):
        try:
            changed(old)
        except Exception:
            if once('operate-changed'):
                log_error('local-battle-operate-changed-error', rail=rail, mode=mode)
    debug('local-battle-fire-mode', rail=rail, mode=mode)
    return True


def auto_attach(player, slot):
    try:
        record = getattr(player, 'dtsWeapon%d' % slot)
        gun = int(record['weaponID'])
    except Exception:
        return []
    if not gun:
        return []
    best = {}
    for comp in bag_items(player):
        fit = comp_fits(comp, gun)
        if fit is None:
            continue
        field, priority = fit
        if record[field]:
            continue
        if field not in best or priority > best[field][1]:
            best[field] = (comp, priority)
    attached = []
    for field, (comp, _priority) in best.items():
        try:
            previous = int(record[field])
            record[field] = comp
            player.onDelDtsFoldedItem(comp, 1)
            player.onWearDtsGunComp(slot, COMP_FIELDS.index(field), previous)
            attached.append(comp)
        except Exception:
            log_error('local-battle-attach-error', comp=comp, slot=slot)
    if attached:
        log('local-battle-attach', slot=slot, gun=gun, comps=attached)
        show_attach_tip(slot, attached, gun)
    return attached


def attach_everywhere(player):
    order = [getattr(player, 'dtsCurWeapon', 0)] + list(GUN_SLOTS + (PISTOL_SLOT,))
    seen = []
    for slot in order:
        if slot in seen or slot not in GUN_SLOTS + (PISTOL_SLOT,):
            continue
        seen.append(slot)
        auto_attach(player, slot)


def strip_comps(player, record):
    for field in COMP_FIELDS:
        try:
            comp = int(record[field])
        except Exception:
            continue
        if comp:
            add_item(player, comp, 1)
            record[field] = 0


def remove_gun(player, slot):
    try:
        record = getattr(player, 'dtsWeapon%d' % slot)
    except Exception:
        return 0
    old = int(record['weaponID'] or 0)
    strip_comps(player, record)
    record['weaponID'] = 0
    bag = weapon_bag(player)
    weapons = getattr(bag, '_idx2weapon_map', None)
    if isinstance(weapons, dict):
        weapons.pop(slot, None)
    if getattr(player, 'dtsCurWeapon', None) == slot:
        switch_weapon(player, MELEE_SLOT)
    try:
        player.onDiscardGun()
    except Exception:
        log_error('local-battle-remove-gun-error', slot=slot)
    return old


GEAR_FIELDS = {'PropTypebulletProofVest': 'bullletProofVest', 'PropTypebulletProofHelmet': 'bullletProofHelmet'}
GEAR_LOOKS = {'bullletProofVest': 'dtsVest', 'bullletProofHelmet': 'dtsHelmet'}
GEAR_TIPS = {'bullletProofVest': 'Armor equipped: %s', 'bullletProofHelmet': 'Helmet equipped: %s'}
ARMOR_STAT = 'AntiDamage'
BACKPACK_TIP = 'Backpack equipped: %s (capacity %d)'
HEAL_TIP = '+%d HP'
HEAL_OVER_TIME_TIP = '+%d HP over %ds'
GENTLE_MEDICINE = 'GentleMedicine'
HORMONE_MEDICINE = 'HormoneMedicine'
HP_FULL_TIP = 'HP is full'
HEALER_GUN = 90050
HEALER_AMMO = 90051
HEALER_SELF_USE = 122
HEALER_TICK = 1.0
HEALER_TIP = '+%d HP over %ds, run faster'
DRINK_TIP = '+%d HP over %ds, speed up'
BACKPACK_CAPACITY = {0: 70, 1: 170, 2: 220, 3: 270}
MEDICINE_KINDS = ('InstantMedicine', 'GentleMedicine', 'HormoneMedicine')


def wear_gear(player, kind, prop):
    field = GEAR_FIELDS[kind]
    try:
        record = getattr(player, field)
        old = dict((key, record[key]) for key in record.keys())
        previous = int(record['itemID'] or 0)
        record['itemID'] = int(prop)
        record['durability'] = int(getattr(prop_type(prop), 'DURABILITY', 100) or 100)
        _ros2_infos(record)
    except Exception:
        log_error('local-battle-gear-error', prop=prop)
        return False
    look = GEAR_LOOKS[field]
    old_look = getattr(player, look, 0)
    try:
        setattr(player, look, int(prop))
    except Exception:
        log_error('local-battle-gear-look-error', prop=prop)
    for callback, args in (('set_' + field, (old,)), ('onWearDtsSafetyGear', (field,)), ('set_' + look, (old_look,))):
        function = getattr(player, callback, None)
        if callable(function):
            try:
                function(*args)
            except Exception:
                if once('gear-' + callback):
                    log_error('local-battle-gear-callback-error', callback=callback)
    tip_text(gear_tip(field, prop))
    if previous:
        drop_at_player(player, previous, 1)
    return True


def armor_stat(prop):
    try:
        return float(getattr(prop_type(prop), ARMOR_STAT, 0.0) or 0.0)
    except Exception:
        return 0.0


def gear_tip(field, prop):
    text = GEAR_TIPS[field] % prop_name(prop)
    stat = armor_stat(prop)
    if stat > 0.0:
        text += ' (-%d%% damage)' % int(round(stat * 100))
    return text


def wear_backpack(player, prop):
    try:
        previous = int(player.dtsPackage or 0)
        player.dtsPackage = int(prop)
    except Exception:
        log_error('local-battle-backpack-error', prop=prop)
        return False
    level = int(getattr(prop_type(prop), 'INDEX', 1) or 1)
    capacity = BACKPACK_CAPACITY.get(level, BACKPACK_CAPACITY[3])
    try:
        player.dtsItemPackage._packageCapacity = capacity
    except Exception:
        pass
    tip_text(BACKPACK_TIP % (prop_name(prop), capacity))
    for callback, args in (('set_dtsPackage', (previous,)), ('onWearDtsPackage', ())):
        function = getattr(player, callback, None)
        if callable(function):
            try:
                function(*args)
            except Exception:
                if once('backpack-' + callback):
                    log_error('local-battle-backpack-callback-error', callback=callback)
    if previous:
        drop_at_player(player, previous, 1)
    return True


def on_wear_comp(player, slot=0, comp=0, *_args, **_kwargs):
    try:
        slot, comp = int(slot), int(comp)
    except Exception:
        return None
    call_later(WEAPON_SWITCH_DELAY, wear_comp, player, slot, comp)
    return None


def wear_comp(player, slot, comp):
    try:
        record = getattr(player, 'dtsWeapon%d' % slot)
        gun = int(record['weaponID'])
    except Exception:
        return False
    fit = comp_fits(comp, gun) if gun else None
    if fit is None:
        tip_text('%s does not fit %s' % (prop_name(comp), prop_name(gun) if gun else 'this slot'))
        return False
    field = fit[0]
    previous = int(record[field] or 0)
    try:
        record[field] = comp
        player.onDelDtsFoldedItem(comp, 1)
        if previous:
            add_item(player, previous, 1)
        player.onWearDtsGunComp(slot, COMP_FIELDS.index(field), previous)
    except Exception:
        log_error('local-battle-wear-comp-error', comp=comp, slot=slot)
        return False
    show_attach_tip(slot, [comp], gun)
    return True


def tip_text(text):
    try:
        import Globals
        Globals.uiMgr.systemJumpTip(text)
        return True
    except Exception:
        return False


def on_use_prop(player, item=0, number=1, *_args, **_kwargs):
    try:
        item, number = int(item), int(number)
    except Exception:
        return None
    call_later(WEAPON_SWITCH_DELAY, use_prop, player, item, number)
    return None


def use_prop(player, item, number):
    kind = prop_kind(item)
    if kind == 'PropTypeBullet':
        gun = current_gun(player)
        try:
            magazine = gun.getCurMagazine()
            need = int(magazine.magazine_capacity) - int(magazine.bullet_count)
        except Exception:
            return False
        count = max(0, min(need, number, int(player.getDtsItemCnt(item))))
        if count:
            finish_reload(player, item, count)
        return bool(count)
    if kind in MEDICINE_KINDS:
        used = heal(player, item)
        if used:
            count_item('uses', item)
        return used
    return False


def heal(player, item):
    kind = prop_type(item)
    name = type(kind).__name__
    if name == HORMONE_MEDICINE:
        return use_healer(player)
    if heals_only(kind) and hp_full(player):
        tip_text(HP_FULL_TIP)
        return False
    effect = int(getattr(kind, 'EFFECT', 0) or 0)
    try:
        player.onDelDtsFoldedItem(item, 1)
    except Exception:
        log_error('local-battle-heal-error', item=item)
        return False
    if name == GENTLE_MEDICINE:
        ticks = max(1, int(getattr(kind, 'TIMES', 1) or 1))
        spread = float(getattr(kind, 'EFFECT_TIME', 0.0) or 0.0)
        speed = int(getattr(kind, 'SPEED_ADD', 0) or 0)
        if speed:
            set_buff(player, 'boostSpeedBuff', speed, spread)
            heal_over_time(player, effect, ticks, spread, True)
            tip_text(DRINK_TIP % (effect * ticks, int(round(spread))))
        else:
            heal_over_time(player, effect, ticks, spread, False)
            tip_text(HEAL_OVER_TIME_TIP % (effect * ticks, int(round(spread))))
        log('local-battle-heal', item=item, over=spread, total=effect * ticks, speed=speed)
        return True
    gained = restore_hp(player, effect)
    if gained:
        tip_text(HEAL_TIP % gained)
    log('local-battle-heal', item=item, gained=gained)
    return True


def heals_only(kind):
    name = type(kind).__name__
    if name not in MEDICINE_KINDS or name == HORMONE_MEDICINE:
        return False
    return not int(getattr(kind, 'SPEED_ADD', 0) or 0)


def hp_full(player):
    try:
        return int(player.hp) >= int(player.maxHp)
    except Exception:
        return False


def heal_over_time(player, effect, ticks, spread, show_bar):
    every = spread / ticks if spread > 0.0 else 0.0
    if show_bar:
        add_pending_hp(player, effect * ticks)
    for tick in range(ticks):
        call_later(every * (tick + 1), heal_tick, player, effect, show_bar)
    return True


def heal_tick(player, effect, show_bar):
    gained = restore_hp(player, effect)
    if show_bar:
        add_pending_hp(player, -effect)
    return gained


_boost = {'pending': 0}
_buffs = {}


def add_pending_hp(player, amount):
    _boost['pending'] = max(0, _boost['pending'] + int(amount))
    value = _boost['pending']
    try:
        player.tmpHP = value
    except Exception:
        pass
    try:
        player.onSyncTmpHp(value)
    except Exception:
        if once('sync-tmp-hp'):
            log_error('local-battle-tmp-hp-error')
    return value


def set_buff(player, attr, value, seconds):
    token = _buffs.get(attr, (0, 0))[0] + 1
    _buffs[attr] = (token, value)
    change_prop(player, attr, value)
    call_later(seconds, end_buff, player, attr, token)
    return token


def end_buff(player, attr, token):
    if _buffs.get(attr, (None,))[0] != token:
        return False
    _buffs.pop(attr, None)
    change_prop(player, attr, 0)
    return True


def change_prop(player, attr, value):
    old = getattr(player, attr, 0)
    try:
        setattr(player, attr, value)
    except Exception:
        if once('buff-' + attr):
            log_error('local-battle-buff-error', attr=attr)
        return False
    changed = getattr(player, 'set_' + attr, None)
    if callable(changed):
        try:
            changed(old)
        except Exception:
            if once('buff-callback-' + attr):
                log_error('local-battle-buff-callback-error', attr=attr)
    return True


def healer_bullet():
    module = _properties_module()
    try:
        return module.getGunBulletData(HEALER_GUN)
    except Exception:
        return None


def use_healer(player):
    bag = weapon_bag(player)
    try:
        magazine = bag.getWeapon(PISTOL_SLOT).getCurMagazine()
        if int(magazine.bullet_count) <= 0:
            return False
        magazine.decBulletFromMagazine()
    except Exception:
        log_error('local-battle-healer-error')
        return False
    bullet = healer_bullet()
    recovery = int(float(getattr(bullet, 'RECOVERY', 60) or 60))
    seconds = float(getattr(bullet, 'BUFF_TIME', 30) or 30)
    ticks = max(1, int(seconds / HEALER_TICK))
    set_buff(player, 'hormoneGunRunBuff', int(getattr(bullet, 'RUN_BUFF_EFFECT', 50) or 0), seconds)
    set_buff(player, 'hormoneGunJumpBuff', int(getattr(bullet, 'JUMP_BUFF_EFFECT', 22) or 0), seconds)
    per_tick = float(recovery) / ticks
    whole = [int(round(per_tick * (tick + 1))) - int(round(per_tick * tick)) for tick in range(ticks)]
    add_pending_hp(player, recovery)
    every = seconds / ticks
    for tick, amount in enumerate(whole):
        call_later(every * (tick + 1), heal_tick, player, amount, True)
    tip_text(HEALER_TIP % (recovery, int(round(seconds))))
    log('local-battle-healer', recovery=recovery, seconds=seconds)
    return True


MED_SING_SECONDS = {101: 4.0, 117: 4.0, 105: 4.0, 106: 4.0, 107: 4.0, 115: 4.0, 119: 4.0,
                    102: 6.0, 108: 6.0, 121: 6.0, 103: 8.0, 104: 8.0, 120: 8.0, 122: 3.0}
FULL_HP_REFUSE_DELAY = 0.05
DEFAULT_SING_SECONDS = 5.0
PROP_RENAMES = {104: ('Baterbonia Kit', 'Using Baterbonia Kit')}
_sing = {'token': 0}


SING_SLACK = 1.5


def on_start_prop_sing(player, item=0, number=1, *_args, **_kwargs):
    try:
        item, number = int(item), int(number or 1)
    except Exception:
        return None
    if heals_only(prop_type(item)) and hp_full(player):
        _sing['active'] = None
        call_later(FULL_HP_REFUSE_DELAY, refuse_prop_sing, player, item)
        return None
    install_sing_finish(player)
    _sing['token'] += 1
    token = _sing['token']
    _sing['active'] = token
    _sing['use'] = (item, number)
    emit('sing', {'on': 1, 'item': item})          # the others see the medkit / bandage / drink in use
    call_later(sing_seconds(item) + SING_SLACK, finish_prop_sing, player, token, item, number)
    return None


def sing_seconds(item):
    seconds = MED_SING_SECONDS.get(item, DEFAULT_SING_SECONDS)
    try:
        listed = float(_properties_module().getBattleGroundPropData(item).SING_TIME or 0.0)
    except Exception:
        listed = 0.0
    return max(seconds, listed)


def refuse_prop_sing(player, item):
    try:
        player.onPropSingInterrupt(item)
    except Exception:
        if once('prop-sing-refuse'):
            log_error('local-battle-prop-sing-refuse-error', item=item)
    _sing['active'] = None
    tip_text(HP_FULL_TIP)
    return True


def finish_prop_sing(player, token, item, number):
    if _sing.get('active') != token:
        return False
    _sing['active'] = None
    emit('sing', {'on': 0, 'item': item})
    return use_prop(player, item, number)


def sing_done(player):
    token = _sing.get('active')
    if token is None or not _sing.get('use'):
        return False
    item, number = _sing['use']
    return finish_prop_sing(player, token, item, number)


def install_sing_guard(player):
    """Stop a heal-only item before the client even starts its bar at full HP."""
    cls = type(player) if player is not None else None
    if cls is None or cls.__dict__.get('_rl_sing_guard'):
        return bool(cls)
    original = getattr(cls, 'startPropSing', None)
    if original is None:
        return False

    def start_prop_sing(self, secs, itemID, *args, **kwargs):
        try:
            refuse = heals_only(prop_type(itemID)) and hp_full(self)
        except Exception:
            refuse = False
        if refuse:
            tip_text(HP_FULL_TIP)
            return None
        return original(self, secs, itemID, *args, **kwargs)

    try:
        cls.startPropSing = start_prop_sing
        cls._rl_sing_guard = True
    except Exception:
        log_error('local-battle-sing-guard-error')
        return False
    return True


def install_sing_finish(player):
    cls = type(player)
    if cls.__dict__.get('_rl_sing_finish'):
        return True
    original = getattr(cls, 'onPropSingFinish', None)
    if original is None:
        return False

    def on_prop_sing_finish(self, *args, **kwargs):
        try:
            result = original(self, *args, **kwargs)
        finally:
            sing_done(self)
        return result

    try:
        cls.onPropSingFinish = on_prop_sing_finish
        cls._rl_sing_finish = True
    except Exception:
        log_error('local-battle-sing-hook-error')
        return False
    return True


def on_cancel_prop_sing(player, *_args, **_kwargs):
    if _sing.get('active') is not None:
        emit('sing', {'on': 0, 'item': (_sing.get('use') or (0,))[0]})
    _sing['active'] = None
    return None


def rename_props():
    module = _properties_module()
    renamed = []
    for prop, (name, using) in PROP_RENAMES.items():
        try:
            data = module.getBattleGroundPropData(prop)
            data.NAME = name
            data.PROP_TYPE.SING_TXT = using
            renamed.append(prop)
        except Exception:
            if once('rename-%d' % prop):
                log_error('local-battle-rename-error', prop=prop)
    return renamed


def restore_hp(player, amount):
    try:
        old = int(player.hp)
        top = int(player.maxHp)
    except Exception:
        return 0
    if old <= 0:
        return 0
    new = min(top, old + int(amount))
    if new == old:
        return 0
    player.hp = new
    changed = getattr(player, 'set_hp', None)
    if callable(changed):
        try:
            changed(old)
        except Exception:
            if once('heal-set-hp'):
                log_error('local-battle-heal-callback-error')
    return new - old


GUN_PROPERTY_TABLES = ('dtsGunCompPropertyDataDict', 'dtsGunCompExtraPropertyDataDict')


def on_exchange_long_gun(player, *_args, **_kwargs):
    call_later(WEAPON_SWITCH_DELAY, exchange_long_gun, player)
    return None


def magazine_count(player, slot):
    try:
        return int(weapon_bag(player).getWeapon(slot).getCurMagazine().bullet_count)
    except Exception:
        return 0


def exchange_long_gun(player):
    try:
        first, second = player.dtsWeapon0, player.dtsWeapon1
        keys = list(first.keys())
        guns = (int(first['weaponID'] or 0), int(second['weaponID'] or 0))
    except Exception:
        return False
    if not any(guns):
        return False
    loaded = dict((slot, magazine_count(player, slot)) for slot in GUN_SLOTS)
    swap_records(first, second, keys)
    current = getattr(player, 'dtsCurWeapon', MELEE_SLOT)
    if current in GUN_SLOTS:
        player.dtsCurWeapon = GUN_SLOTS[1 - GUN_SLOTS.index(current)]
    if all(guns):
        for name in GUN_PROPERTY_TABLES:
            table = getattr(player, name, None)
            if isinstance(table, dict):
                for slot in GUN_SLOTS:
                    table.setdefault(slot, {})
        try:
            player.onExchangeLongGun()
        except Exception:
            log_error('local-battle-exchange-gun-error')
            swap_records(first, second, keys)
            player.dtsCurWeapon = current
            return False
    else:
        move_single_gun(player, loaded)
    log('local-battle-exchange-gun', guns=list(guns))
    return True


def swap_records(first, second, keys):
    before = dict((key, first[key]) for key in keys)
    for key in keys:
        first[key] = second[key]
        second[key] = before[key]


def move_single_gun(player, loaded):
    bag = weapon_bag(player)
    weapons = getattr(bag, '_idx2weapon_map', None)
    for slot in GUN_SLOTS:
        if isinstance(weapons, dict):
            weapons.pop(slot, None)
    for slot in GUN_SLOTS:
        try:
            player.onWearDtsWeapon(slot)
        except Exception:
            log_error('local-battle-move-gun-error', slot=slot)
    for slot in GUN_SLOTS:
        count = loaded.get(GUN_SLOTS[1 - GUN_SLOTS.index(slot)], 0)
        if not count:
            continue
        try:
            gun = bag.getWeapon(slot)
            bullet = gun_bullet(int(getattr(player, 'dtsWeapon%d' % slot)['weaponID']))
            missing = count - int(gun.getCurMagazine().bullet_count)
            if bullet and missing > 0:
                bag.supplyWeaponMagazine(slot, bullet, missing)
        except Exception:
            pass
    switch_weapon(player, getattr(player, 'dtsCurWeapon', MELEE_SLOT))


def comp_slot(where):
    where = str(where or '').strip(QUOTES)
    if not where.startswith('dtsWeapon'):
        return None
    try:
        return int(where[len('dtsWeapon'):])
    except Exception:
        return None


def on_exchange_gun_component(player, from_slot=0, to_slot=0, field='', *_args, **_kwargs):
    try:
        from_slot, to_slot = int(from_slot), int(to_slot)
    except Exception:
        return None
    call_later(WEAPON_SWITCH_DELAY, exchange_gun_component, player, from_slot, to_slot,
               str(field or '').strip(QUOTES))
    return None


def exchange_gun_component(player, from_slot, to_slot, field):
    if field not in COMP_FIELDS or from_slot == to_slot:
        return False
    try:
        source = getattr(player, 'dtsWeapon%d' % from_slot)
        target = getattr(player, 'dtsWeapon%d' % to_slot)
        comp = int(source[field] or 0)
        target_gun = int(target['weaponID'] or 0)
        source_gun = int(source['weaponID'] or 0)
        previous = int(target[field] or 0)
    except Exception:
        return False
    if not comp or not target_gun:
        return False
    if comp_fits(comp, target_gun) is None:
        tip_text('%s does not fit %s' % (prop_name(comp), prop_name(target_gun)))
        return False
    target[field] = comp
    source[field] = 0
    if previous:
        if source_gun and comp_fits(previous, source_gun) is not None:
            source[field] = previous
        else:
            add_item(player, previous, 1)
    index = COMP_FIELDS.index(field)
    try:
        player.onWearDtsGunComp(to_slot, index, previous)
        player.onWearDtsGunComp(from_slot, index, comp)
    except Exception:
        log_error('local-battle-exchange-comp-error', field=field)
        return False
    try:
        player.onExchangeGunComponent(from_slot, True, comp, to_slot, bool(previous), previous, field)
    except Exception:
        pass
    show_attach_tip(to_slot, [comp], target_gun)
    return True


def on_take_off_comp(player, where='', field='', *_args, **_kwargs):
    call_later(WEAPON_SWITCH_DELAY, take_off_comp, player, where, field, False)
    return None


def on_drop_comp(player, where='', field='', *_args, **_kwargs):
    call_later(WEAPON_SWITCH_DELAY, take_off_comp, player, where, field, True)
    return None


def on_unload_comps(player, where='', *_args, **_kwargs):
    call_later(WEAPON_SWITCH_DELAY, unload_comps, player, where)
    return None


def unload_comps(player, where):
    removed = [field for field in COMP_FIELDS if take_off_comp(player, where, field, False)]
    return removed


def take_off_comp(player, where, field, drop):
    slot = comp_slot(where)
    field = str(field or '').strip(QUOTES)
    if slot is None or field not in COMP_FIELDS:
        return False
    try:
        record = getattr(player, 'dtsWeapon%d' % slot)
        previous = int(record[field] or 0)
    except Exception:
        return False
    if not previous:
        return False
    record[field] = 0
    if drop:
        drop_at_player(player, previous, 1)
    else:
        add_item(player, previous, 1)
    try:
        player.onDiscardDtsGunComp('dtsWeapon%d' % slot, field, previous)
    except Exception:
        try:
            player.onWearDtsGunComp(slot, COMP_FIELDS.index(field), previous)
        except Exception:
            log_error('local-battle-take-off-comp-error', slot=slot, field=field)
            return False
    return True


def pick_up(entity, args):
    player = current_player()
    entity_id = getattr(entity, 'id', None)
    record = _loot.get(entity_id)
    if player is None or record is None:
        return False
    prop = record['prop']
    taken = requested_amount(args, record['amount'])
    kind = grant_prop(player, prop, taken)
    if kind is None:
        return False                            # refused: it stays on the ground
    note_collected(prop)
    count_item('pickups', prop, taken)
    report_take(record.get('key'), taken)
    left = record['amount'] - taken
    if left > 0:
        record['amount'] = left
        try:
            entity.syncAmount(left)
        except Exception:
            pass
    else:
        remove_loot(entity_id)
    log('local-battle-pickup', prop=prop, kind=kind, amount=taken, left=max(0, left))
    return True


def count_item(field, prop, amount=1):
    """Battle items picked up / used this round, by prop ID: the Special
    Distinction missions ("Pick up 3 AWM", "Use 5 Med Kits", features/manual.py)."""
    try:
        key, amount = str(int(prop)), int(amount)
    except Exception:
        return False
    if amount <= 0:
        return False
    counts = _round.setdefault(field, {})
    counts[key] = counts.get(key, 0) + amount
    return True


def note_collected(prop):
    """Different supplies picked up this round (ground loot, boxes): the
    result's collectCount (STATS, the Activity task "Fully Armed")."""
    picked = _round.setdefault('picked', set())
    picked.add(prop)
    _round['collected'] = len(picked)
    return _round['collected']


def grant_prop(player, prop, taken):
    kind = prop_kind(prop)
    if kind == 'PropTypeGun':
        equip_gun(player, prop)
    elif kind in COMP_KINDS:
        add_item(player, prop, taken)
        attach_everywhere(player)
    elif kind in GEAR_FIELDS:
        wear_gear(player, kind, prop)
    elif kind == 'PropTypePackage':
        wear_backpack(player, prop)
    elif kind == 'PropTypeAppearance' and cloth_slot(prop):
        if wear_cloth(player, prop) is False:
            return None                         # not taken: it stays on the ground / in the box
    elif kind == 'PropTypeColdWeapon':
        equip_slot_item(player, MELEE_SLOT, prop)
    elif kind == 'PropTypeBombWeapon':
        add_item(player, prop, taken)
        if not getattr(player, 'dtsWeapon%d' % BOMB_SLOT, 0):
            equip_slot_item(player, BOMB_SLOT, prop)
    else:
        add_item(player, prop, taken)
    return kind


HERITAGE_CLASS = 'DtsPlayerHeritage'
HERITAGE_AMMO_STACKS = 2
HERITAGE_EXTRAS = 3
HERITAGE_LIFT = 0.2
_heritages = {}


def install_heritage_cell():
    module = sys.modules.get(HERITAGE_CLASS)
    if module is None:
        try:
            module = __import__(HERITAGE_CLASS)
        except Exception:
            return False
    cls = getattr(module, HERITAGE_CLASS, None)
    if not isinstance(cls, type):
        return False
    if cls.__dict__.get('_rl_heritage_cell'):
        return True
    original = cls.__getattribute__

    def heritage_getattribute(self, name):
        if name == 'cell':
            try:
                entity_id = original(self, 'id')
            except Exception:
                entity_id = None
            if entity_id in _heritages:
                return HeritageCell(self)
        return original(self, name)

    try:
        cls.__getattribute__ = heritage_getattribute
        cls._rl_heritage_cell = True
    except Exception:
        log_error('local-battle-heritage-cell-error')
        return False
    return True


class HeritageCell(object):
    def __init__(self, entity):
        self.entity = entity

    def tryPickUp(self, uuid=None, *args):
        call_later(POSE_ECHO_DELAY, take_from_box, self.entity, uuid, args)

    def tryPickUpForTeammate(self, uuid=None, *args):
        call_later(POSE_ECHO_DELAY, take_from_box, self.entity, uuid, args)

    def __getattr__(self, name):
        if name == DESTROYED_FLAG:
            return True
        if name.startswith('__'):
            raise AttributeError(name)
        return silent_call


def heritage_items(randomizer):
    gun = randomizer.choice(LOOT_GUNS)
    items = [(gun, 1)]
    bullet = gun_bullet(gun)
    if bullet:
        items.extend([(bullet, LOOT_AMMO_STACK)] * HERITAGE_AMMO_STACKS)
    for _index in range(HERITAGE_EXTRAS):
        items.append(randomizer.choice(LOOT_SINGLES))
    return dict(('heritage-%d' % index, [prop, amount, {}]) for index, (prop, amount) in enumerate(items))


def drop_heritage(battle_id, name, point, contents):
    """The death box of a player who died: what they carried (their guns,
    attachments, worn gear, everything in the bag) - nothing when they had
    nothing.  The same box, the same items in the same order, in every
    window (the victim's window sends them), so what is taken out of it in
    one is gone in all."""
    items = dict(('heritage-%d' % index, [int(prop), int(amount), {}])
                 for index, (prop, amount) in enumerate(contents or []) if int(prop) and int(amount) > 0)
    key = 'b%s' % battle_id
    if not items or key in _heritage_keys:
        return None
    try:
        import BigWorld
    except Exception:
        return None
    x, y, z = _point(point)
    ground = ground_height(x, z) or y
    install_heritage_cell()
    space = BATTLE['space'] or getattr(current_player(), 'spaceID', 0)
    try:
        made = BigWorld.createEntity(HERITAGE_CLASS, space, 0, (x, ground + HERITAGE_LIFT, z), (0.0, 0.0, 0.0),
                                     {'name': str(name or 'Player'), 'items': items})
    except Exception:
        log_error('local-battle-heritage-error', target=battle_id)
        return None
    entity_id = getattr(made, 'id', made)
    _heritage_keys.add(key)
    _heritages[entity_id] = items
    share_box(entity_id, key, items)
    log('local-battle-heritage', box=entity_id, owner=battle_id, items=[entry[0] for entry in items.values()])
    return entity_id


_heritage_keys = set()
DEFAULT_MELEE = 1301                    # bare hands: not an item


def carried_items(player):
    """What this player has on them, as (prop, amount): the guns and the
    attachments on them, the melee weapon, worn helmet / vest / backpack,
    and everything in the bag."""
    items = []
    for slot in GUN_SLOTS + (PISTOL_SLOT, MELEE_SLOT):
        record = getattr(player, 'dtsWeapon%d' % slot, None)
        gun = weapon_id(record)
        if not gun or gun == DEFAULT_MELEE:
            continue
        items.append((gun, 1))
        if hasattr(record, 'keys'):
            for field in COMP_FIELDS:
                try:
                    comp = int(record[field] or 0)
                except Exception:
                    comp = 0
                if comp:
                    items.append((comp, 1))
    for field in WORN_GEAR:
        prop = weapon_id(getattr(player, field, 0))
        if prop:
            items.append((prop, 1))
    for item in sorted(bag_items(player)):
        try:
            amount = carried(player, int(item))
        except Exception:
            amount = 0
        if amount > 0:
            items.append((int(item), amount))
    return items


def leave_my_heritage(player, point=None):
    """We died: our death box, here and in every other window."""
    if on_island_stage():
        return None
    me = BATTLE.get('entity_id')
    items = carried_items(player)
    try:
        where = _point(point or player.position)
    except Exception:
        return None
    emit('heritage', {'items': [[prop, amount] for prop, amount in items],
                      'pos': [round(value, 2) for value in where], 'name': avatar_name(player)})
    return drop_heritage(me, avatar_name(player), where, items)


def fill_heritages():
    for entity_id, items in list(_heritages.items()):
        box = vehicle_entity(entity_id)
        if box is None or getattr(box, 'items', None):
            continue
        try:
            box.items = dict(items)
        except Exception:
            if once('heritage-fill'):
                log_error('local-battle-heritage-fill-error')


def take_from_box(box, uuid, args):
    player = current_player()
    items = dict(getattr(box, 'items', None) or {})
    entry = items.get(uuid)
    if player is None or entry is None:
        return False
    prop, amount = int(entry[0]), int(entry[1])
    taken = requested_amount(args, amount)
    kind = grant_prop(player, prop, taken)
    if kind is None:
        return False                            # refused (an outfit for the other gender): left in the box
    note_collected(prop)
    box_key = _boxes.get(box.id, {}).get('key')
    if box_key:
        report_take('%s:%s' % (box_key, uuid), taken)
    left = amount - taken
    if left > 0:
        items[uuid] = [prop, left] + list(entry[2:3])
    else:
        items.pop(uuid, None)
    _heritages[box.id] = items
    try:
        box.resetItems(items)
    except Exception:
        box.items = items
    if not items:
        empty_box(box)
    log('local-battle-heritage-pickup', box=box.id, prop=prop, kind=kind, amount=taken)
    return True


def empty_box(box):
    _heritages.pop(box.id, None)
    _boxes.pop(box.id, None)
    try:
        import BigWorld
        BigWorld.destroyEntity(box.id)
    except Exception:
        log_error('local-battle-heritage-destroy-error')


def gun_slot_free(player, slot):
    try:
        return not int(getattr(player, 'dtsWeapon%d' % slot)['weaponID'])
    except Exception:
        return False


def _ros2_infos(record):
    # fields of the stock 2022 client; this build's records may not have them (KeyError)
    for key in ('ros2WeaponInGameStaticInfos', 'ros2WeaponInGameDynamicInfos'):
        try:
            record[key] = {}
        except Exception:
            pass


def equip_gun(player, prop):
    if prop in PISTOL_PROPS:
        slot = PISTOL_SLOT
    else:
        free = [slot for slot in GUN_SLOTS if gun_slot_free(player, slot)]
        current = getattr(player, 'dtsCurWeapon', 0)
        slot = free[0] if free else (current if current in GUN_SLOTS else GUN_SLOTS[0])
    old = remove_gun(player, slot) if not gun_slot_free(player, slot) else 0
    try:
        record = getattr(player, 'dtsWeapon%d' % slot)
        record['weaponID'] = prop
        _ros2_infos(record)
        player.onWearDtsWeapon(slot)
    except Exception:
        log_error('local-battle-equip-error', prop=prop, slot=slot)
        return None
    if old:
        drop_at_player(player, old, 1)
    fill_magazine(player, slot)
    auto_attach(player, slot)
    if getattr(player, 'dtsCurWeapon', MELEE_SLOT) not in GUN_SLOTS + (PISTOL_SLOT,):
        switch_weapon(player, slot)
    return slot


def equip_slot_item(player, slot, prop):
    try:
        old = int(getattr(player, 'dtsWeapon%d' % slot) or 0)
        setattr(player, 'dtsWeapon%d' % slot, prop)
        player.onWearDtsWeapon(slot)
    except Exception:
        log_error('local-battle-equip-error', prop=prop, slot=slot)
        return None
    if slot == MELEE_SLOT and old and old != UNARMED:
        drop_at_player(player, old, 1)
    return slot


def drop_at_player(player, prop, amount):
    try:
        position = player.position
        yaw = float(getattr(player, 'yaw', 0.0) or 0.0)
        x = position.x + LOOT_DROP_DISTANCE * math.sin(yaw)
        z = position.z + LOOT_DROP_DISTANCE * math.cos(yaw)
        entity_id = spawn_loot(prop, amount, x, z, position.y)
        if entity_id is not None:
            share_drop(entity_id, prop, amount, (x, position.y, z))
        return entity_id
    except Exception:
        log_error('local-battle-drop-error', prop=prop)
        return None


def on_discard_prop(player, item=0, number=1, where=None, *_args, **_kwargs):
    try:
        item, number = int(item), int(number)
    except Exception:
        return None
    call_later(POSE_ECHO_DELAY, discard, player, item, number, where)
    return None


def discard(player, item, number, where):
    where = str(where or '').strip(QUOTES)
    if where in GEAR_LOOKS or where.startswith(CLOTH_PREFIX) or where == 'dtsPackage':
        # Worn things: taken off, not looked for in the bag (it stayed on
        # you and lay on the ground as well - a second helmet / outfit).
        if not take_off_worn(player, where):
            log('local-battle-discard-skipped', item=item, where=where, reason='not worn')
            return False
        number = 1
    elif where.startswith('dtsWeapon'):
        try:
            slot = int(where[len('dtsWeapon'):])
            value = getattr(player, where)
        except Exception:
            return False
        if hasattr(value, 'keys'):
            remove_gun(player, slot)
        else:
            try:
                setattr(player, where, UNARMED if slot == MELEE_SLOT else 0)
                player.onWearDtsWeapon(slot)
                if slot == MELEE_SLOT:
                    player.onDiscardColdWeapon()
            except Exception:
                log_error('local-battle-discard-error', item=item, where=where)
                return False
            if getattr(player, 'dtsCurWeapon', None) == slot and slot != MELEE_SLOT:
                switch_weapon(player, MELEE_SLOT)
        number = 1
    else:
        try:
            player.onDelDtsFoldedItem(item, number)
        except Exception:
            log_error('local-battle-discard-error', item=item, where=where)
            return False
    drop_at_player(player, item, number)
    log('local-battle-discard', item=item, amount=number, where=where or 'bag')
    return True


CLOTH_PREFIX = 'cloth'
NOT_YOUR_SIZE_TIP = "That outfit doesn't fit your character."


def take_off_worn(player, where):
    if where in GEAR_LOOKS:
        return take_off_gear(player, where)
    if where == 'dtsPackage':
        return take_off_backpack(player)
    return bool(take_off_cloth(player, where))


def take_off_cloth(player, slot):
    """Avatar.set_clothN (_before_wear_cloth -> _set_props) redraws the body
    without it; iDtsEquip.onWearDtsAppearance refreshes the bag's slots."""
    try:
        old = int(getattr(player, slot) or 0)
    except Exception:
        return 0
    if not old:
        return 0
    try:
        setattr(player, slot, 0)
    except Exception:
        log_error('local-battle-cloth-error', slot=slot)
        return 0
    cloth_callbacks(player, slot, old, old)
    log('local-battle-cloth-off', slot=slot, cloth=old)
    return old


def cloth_callbacks(player, slot, old, item):
    for callback, args in (('set_' + slot, (old,)), ('onWearDtsAppearance', (item,))):
        function = getattr(player, callback, None)
        if callable(function):
            try:
                function(*args)
            except Exception:
                if once('cloth-' + callback):
                    log_error('local-battle-cloth-callback-error', callback=callback)


def cloth_slot(prop):
    try:
        slot = str(_properties_module().getBattleGroundPropData(int(prop)).PROP_TYPE.SLOT or '')
    except Exception:
        return None
    return slot if slot.startswith(CLOTH_PREFIX) else None


def cloth_gender(prop):
    """A lobby outfit piece is cut for one gender (its hall prop's GENDER:
    1 male, 2 female); battle clothes (the Ghillie Suit) fit everyone."""
    try:
        return int(getattr(_properties_module().getDtsHallPropData(int(prop)).PROP_TYPE, 'GENDER', 0) or 0)
    except Exception:
        return 0


def battle_gender():
    gender = BATTLE.get('gender')
    if gender:
        return gender
    data = None
    try:
        data = LOBBY.character_data(BATTLE.get('character_type') or 0)
    except Exception:
        data = None
    return int(getattr(data, 'GENDER', 0) or 0)


def fits_you(prop):
    wanted = cloth_gender(prop)
    gender = battle_gender()
    return not wanted or not gender or wanted == gender


def wear_cloth(player, prop):
    """Picking clothes up puts them on (what was in that slot drops); one
    cut for the other gender would leave the body without that part, so it
    stays where it lies."""
    slot = cloth_slot(prop)
    if slot is None:
        return None
    if not fits_you(prop):
        tip_text(NOT_YOUR_SIZE_TIP)
        return False
    try:
        old = int(getattr(player, slot) or 0)
        setattr(player, slot, int(prop))
    except Exception:
        log_error('local-battle-cloth-error', slot=slot, prop=prop)
        return False
    cloth_callbacks(player, slot, old, prop)
    if old and old != prop:
        drop_at_player(player, old, 1)
    log('local-battle-cloth-on', slot=slot, cloth=prop, dropped=old or None)
    return True


VEHICLE_FLEET = (
    ('LandCar', 25000, 115501),
    ('LandCar', 25001, 115500),
    ('LandCar', 25003, 115503),
    ('LandCar', 25010, 130002),
    ('LandCar', 25100, 130003),
    ('LandCar', 31002, 131002),
    ('LandCar', 31004, 131004),
)
VEHICLE_COUNT = 10
VEHICLE_RADIUS = 800.0
VEHICLE_MIN_RADIUS = 100.0
VEHICLE_SPACING = 80.0
VEHICLE_TRIES = 40
VEHICLE_LIFT = 2.0
VEHICLE_CLEARANCE = 15.0
VEHICLE_PROBE_HEIGHT = 300.0
VEHICLE_FOOTPRINT = 25.0
VEHICLE_ENTER_RANGE = 45.0
VEHICLE_WHEELS = 4
VEHICLE_WHEEL_HP = 100
VEHICLE_DRIVER_SOCKET = 'Driver'
VEHICLE_CLASSES = ('LandCar', 'LandBoat')
VEHICLE_CAMP = 30
VEHICLE_MAX_TILT = 80.0
VEHICLE_BUFFS = ('maxSpeedBuff', 'throttleBuff', 'driveForceBuff')
DAMAGE_TEXT_COMP = 'DamageTextJumpComp'
DAMAGE_TEXT_LIFT = 10.0
VEHICLE_CONTROLLER = 'VehicleFPController'
VEHICLE_CONTROLLER_MODULE = 'vehicle.logic_ctrls.vehicle_player.VehicleFPController'
VEHICLE_REBOARD_DELAY = 1.0
VEHICLE_COAST_POLL = 0.25
VEHICLE_COAST_LIMIT = 20.0
VEHICLE_PARK_SPEED = 3.0
VEHICLE_EXIT_SIDE = 28.0
VEHICLE_EXIT_PROBE = 40.0
VEHICLE_EXIT_LIFT = 1.0
VEHICLE_EXIT_DELAY = 0.1
VEHICLE_DEFAULT_DAMAGE = 30.0
_vehicles = {}


def vehicle_numbers(land, tps):
    module = _properties_module()
    hp, speed, fuel = 1000, 0.0, 0.0
    try:
        hp = int(module.getLandVehicleData(land).hp or hp)
    except Exception:
        pass
    try:
        data = module.getVehicleData(tps)
        speed = float(getattr(data, 'VEHICLE_MAX_SPEED', 0.0) or 0.0)
        fuel = float(getattr(getattr(data, 'FUEL_DATA', None), 'CAPACITY', 0.0) or 0.0)
    except Exception:
        pass
    return hp, speed, fuel


def surface_clear(x, z):
    ground = None
    for dx, dz in ((0.0, 0.0), (VEHICLE_FOOTPRINT, 0.0), (-VEHICLE_FOOTPRINT, 0.0),
                   (0.0, VEHICLE_FOOTPRINT), (0.0, -VEHICLE_FOOTPRINT)):
        height = point_clear(x + dx, z + dz)
        if height is None:
            return None
        if ground is None:
            ground = height
        elif abs(height - ground) > VEHICLE_CLEARANCE:
            return None
    return ground


def point_clear(x, z):
    ground = ground_height(x, z)
    if not ground:
        return None
    physics_module = sys.modules.get('libclaudia.Classes.Physics')
    ray_module = sys.modules.get('libclaudia.Classes.Ray')
    if physics_module is None or ray_module is None:
        return ground
    try:
        vector = physics_module.Vector3
        hit = ray_module.RaycastHit()
        top = ground + VEHICLE_PROBE_HEIGHT
        if physics_module.Physics.RaycastWithScene(vector(x, top, z), vector(0.0, -1.0, 0.0), hit,
                                                   VEHICLE_PROBE_HEIGHT * 2.0):
            if top - float(hit.distance) > ground + VEHICLE_CLEARANCE:
                return None
    except Exception:
        return ground
    return ground


def install_vehicle_cell():
    for class_name in VEHICLE_CLASSES:
        module = sys.modules.get(class_name)
        if module is None:
            try:
                module = __import__(class_name)
            except Exception:
                continue
        cls = getattr(module, class_name, None)
        if not isinstance(cls, type) or cls.__dict__.get('_rl_vehicle_cell') == VEHICLE_CELL_VERSION:
            continue
        original = cls.__dict__.get('_rl_vehicle_original') or cls.__getattribute__

        def vehicle_getattribute(self, name, _original=original):
            if name == 'cell':
                try:
                    entity_id = _original(self, 'id')
                except Exception:
                    entity_id = None
                if entity_id in _vehicles:
                    return SilentCell(entity_id)
            return _original(self, name)

        try:
            if not cls.__dict__.get('_rl_vehicle_cell'):
                cls._rl_vehicle_original = original
            cls.__getattribute__ = vehicle_getattribute
            cls._rl_vehicle_cell = VEHICLE_CELL_VERSION
        except Exception:
            log_error('local-battle-vehicle-cell-error', entity_class=class_name)


class SilentCell(object):
    """A car's server side: nothing - but for what the other players must
    hear and feel (CAR_CELL_CALLS): the horn, crashes, running into them."""

    def __init__(self, entity_id=None):
        self._rl_entity = entity_id

    def __getattr__(self, name):
        if name == DESTROYED_FLAG:
            return True
        if name.startswith('__') or name.startswith('_rl'):
            raise AttributeError(name)
        handler = CAR_CELL_CALLS.get(name)
        if handler is not None and self._rl_entity is not None:
            entity_id = self._rl_entity
            return lambda *args, **_kwargs: car_cell_call(handler, entity_id, args)
        return silent_call


def silent_call(*_args, **_kwargs):
    return None


PHYSIC_ASSEMBLE_MODULE = 'vehicle.appearance.VehiclePhysicAssemble'


def install_keep_wheels():
    """VehiclePhysicAssemble.onBecomeNoDriver switches the physics car off
    (setEnable(False)) for a car that is not a carry vehicle: online the
    server drove it from then on.  Here the car is still rolling in our own
    physics after a rush exit - without its wheels it slid on and fell
    through the ground (a wreck too).  Our cars keep them."""
    module = sys.modules.get(PHYSIC_ASSEMBLE_MODULE)
    cls = getattr(module, 'VehiclePhysicAssemble', None)
    if not isinstance(cls, type) or cls.__dict__.get('_rl_keep_wheels'):
        return False
    original = cls.__dict__.get('onBecomeNoDriver')
    if original is None:
        return False

    def onBecomeNoDriver(self, *args, **kwargs):
        entity = getattr(self, 'ent', None)
        if getattr(entity, 'id', None) in _vehicles:
            return None
        return original(self, *args, **kwargs)

    try:
        cls.onBecomeNoDriver = onBecomeNoDriver
        cls._rl_keep_wheels = True
    except Exception:
        log_error('local-battle-keep-wheels-error')
        return False
    return True


VEHICLE_CELL_VERSION = 2
CAR_HIT_MIN_KMH = 15.0                  # slower than this, running into someone does not hurt
CAR_HIT_PER_KMH = 1.2                   # damage per km/h above that
CAR_HIT_MAX = 120.0
CAR_HIT_AGAIN = 0.6                     # s: the same one is hit once in this long
CAR_HIT_WEAPON = 'Vehicle'
_car_hits = {}                          # target entity id -> when it was last run into


def car_cell_call(handler, entity_id, args):
    try:
        return handler(entity_id, list(args))
    except Exception:
        if once('car-cell-' + handler.__name__):
            log_error('local-battle-car-cell-error', call=handler.__name__)
        return None


def car_key(entity_id):
    return _vehicles.get(entity_id, {}).get('key')


def car_horn_on(entity_id, _args):
    return emit('car_fx', {'key': car_key(entity_id), 'fx': 'horn'}) if car_key(entity_id) else False


def car_horn_off(entity_id, _args):
    return emit('car_fx', {'key': car_key(entity_id), 'fx': 'quiet'}) if car_key(entity_id) else False


def car_crashed(entity_id, args):
    """iLandVehicle.onHitScene: hitScene(position, impulse) - the impulse
    is the car's mass times how much speed it lost."""
    car = vehicle_entity(entity_id)
    if car is None or not car_key(entity_id) or len(args) < 2:
        return False
    mass = float(getattr(car, 'mass', 0.0) or 0.0) or 1.0
    return emit('car_fx', {'key': car_key(entity_id), 'fx': 'crash',
                           'speed': round(abs(float(args[1] or 0.0)) / mass, 1), 'at': relay_point(args[0])})


def car_ran_into(entity_id, args):
    """iVehicleEntity.msgVehicleHit: vehicleHit(car, position, ids, impulses,
    parts, speeds) - who the car we drive ran into.  Players and bots are
    hurt by how fast it went (the host keeps players' HP); the others hear
    the thud."""
    me = current_player()
    car = vehicle_entity(entity_id)
    if me is None or car is None or len(args) < 3:
        return False
    if not (getattr(me, 'isLandDriver', False) and getattr(me, 'vehicleEntID', 0) == entity_id):
        return False
    speeds = list(args[5]) if len(args) > 5 and isinstance(args[5], (list, tuple)) else []
    kmh = vehicle_speed(car) or (abs(float(speeds[0])) if speeds else 0.0)
    damage = min(CAR_HIT_MAX, max(0.0, (kmh - CAR_HIT_MIN_KMH) * CAR_HIT_PER_KMH))
    now = time.time()
    hurt = 0
    for target_id in list(args[2] or []):
        body = remote_avatar(target_id)
        if body is None or damage <= 0.0 or now - _car_hits.get(target_id, 0.0) < CAR_HIT_AGAIN:
            continue
        _car_hits[target_id] = now
        hurt_avatar(me, body, damage, car.position, CHEST_PART, HIT_SHOOT, weapon_record(0, 0, HIT_SHOOT),
                    CAR_HIT_WEAPON)
        hurt += 1
    if car_key(entity_id) and args[2]:
        emit('car_fx', {'key': car_key(entity_id), 'fx': 'thud', 'speed': round(kmh, 1)})
    log('local-battle-vehicle-hit', vehicle=entity_id, targets=[int(t) for t in list(args[2] or [])][:8],
        kmh=round(kmh, 1), damage=round(damage), hurt=hurt)
    return hurt


def car_nos_on(entity_id, _args):
    log('local-battle-nos', vehicle=entity_id, on=True)
    return emit('car_fx', {'key': car_key(entity_id), 'fx': 'nos'}) if car_key(entity_id) else False


def car_nos_off(entity_id, _args):
    return emit('car_fx', {'key': car_key(entity_id), 'fx': 'nos_end'}) if car_key(entity_id) else False


CAR_NOS_SOCKETS = (('NOS_LEFT_00', 'VEHICLE_NOS_EFFECT_LEFT'), ('NOS_RIGHT_00', 'VEHICLE_NOS_EFFECT_RIGHT'))


def show_nos(car, on):
    """Another player's nitro on our copy of their car: the exhaust flames
    their own car shows (CarFPEffect.startNOS) - ours is drawn by
    CarTPEffect, which has no nitro sockets until they are made here."""
    try:
        effect = car.gameObject.GetComponent('CarTPEffect')
    except Exception:
        return False
    if effect is None:
        return False
    try:
        for socket, field in CAR_NOS_SOCKETS:
            if on and (socket, 0) not in effect.sfxSocketMap:
                path = getattr(effect.vehicleData, field, None)
                if path:
                    effect._doCreatSocketAndBindEff(socket, path, False)
            if (socket, 0) in effect.sfxSocketMap:
                (effect.doSfxPlay if on else effect.stopSfxPlay)(socket, 0)
    except Exception:
        if once('show-nos'):
            log_error('local-battle-show-nos-error')
        return False
    return True


CAR_CELL_CALLS = {
    'onAccStart': car_nos_on,
    'onAccEnd': car_nos_off,
    'playTrumpet': car_horn_on,
    'stopTrumpet': car_horn_off,
    'hitScene': car_crashed,
    'vehicleHit': car_ran_into,
}


def replay_car_fx(data):
    """The horn, a crash, a thud of a car another player drives - on our
    copy of it (VehicleTPSound, as the server's onPlayTrumpet / the hit
    sounds were heard by everyone near)."""
    car = vehicle_entity(_car_keys.get(data.get('key')))
    if car is None:
        return False
    fx = data.get('fx')
    if fx in ('nos', 'nos_end'):
        return show_nos(car, fx == 'nos')
    try:
        sound = car.gameObject.GetComponent('VehicleTPSound')
    except Exception:
        sound = None
    if sound is None:
        return False
    try:
        if fx == 'horn':
            sound.onPlayTrumpet()
        elif fx == 'quiet':
            sound.onStopTrumpet()
        elif fx == 'crash':
            sound._doHitSound(float(data.get('speed') or 0.0), 'SCENE')
        elif fx == 'thud':
            sound._doHitSound(float(data.get('speed') or 0.0), 'FLESH')
        else:
            return False
    except Exception:
        if once('car-fx-' + str(fx)):
            log_error('local-battle-car-fx-error', fx=fx)
        return False
    return True


CAMP_MODULES = ('camp_utils', 'common.camp_utils')
NEUTRAL_CAMP = 0


def install_neutral_camp():
    for name in CAMP_MODULES:
        relation = getattr(sys.modules.get(name), 'CampRelation', None)
        if isinstance(relation, dict):
            if NEUTRAL_CAMP not in relation:
                camps = set(relation)
                for row in relation.values():
                    camps.update(row)
                relation[NEUTRAL_CAMP] = dict((camp, 0) for camp in camps)
            return True
    return False


def spawn_vehicle(class_name, land, tps, x, z, ground, yaw):
    try:
        import BigWorld
    except Exception:
        return None
    install_vehicle_cell()
    install_keep_wheels()
    install_neutral_camp()
    hp, speed, fuel = vehicle_numbers(land, tps)
    space = BATTLE['space'] or getattr(current_player(), 'spaceID', 0)
    properties = {'characterType': land, 'tpsVehicleID': tps, 'mapID': BATTLE['map'], 'hp': hp, 'maxHp': hp,
                  'wheelHp': [VEHICLE_WHEEL_HP] * VEHICLE_WHEELS, 'wheelMaxHp': [VEHICLE_WHEEL_HP] * VEHICLE_WHEELS,
                  'maxSpeed': speed, 'fuelAmount': fuel,
                  # LandCar.__init__: supportNos = not isCarryVehicle.  Unset it
                  # read as a carry vehicle: no nitro button, carry-vehicle drive.
                  'isCarryVehicle': False}
    try:
        made = BigWorld.createEntity(class_name, space, 0, (x, ground + VEHICLE_LIFT, z), (0.0, 0.0, yaw),
                                     properties)
    except Exception:
        if once('vehicle-create'):
            log_error('local-battle-vehicle-error', land=land)
        return None
    entity_id = getattr(made, 'id', made)
    _vehicles[entity_id] = {'land': land, 'tps': tps, 'near': False, 'dead': False, 'prepared': False}
    return entity_id


CAR_CARE_EVERY = 1.0                    # s
CAR_LOD = (10000.0, 10000.5, -1.0)      # the whole car to this far, then not drawn (no middle step)
CAR_SINK = 40.0                         # under the ground by more than this: it fell through
CAR_SINK_PROBE = 2000.0
_car_care = {'at': 0.0}


def car_care(player):
    """Every second, for our cars: drawn whole, and above the ground."""
    me_in = getattr(player, 'vehicleEntID', 0) if getattr(player, 'inLandVehicle', False) else 0
    driven = set(key for key, glide in _car_motion.items() if glide.get('samples'))
    for entity_id, record in list(_vehicles.items()):
        car = vehicle_entity(entity_id)
        if car is None:
            continue
        if not record.get('lod'):
            record['lod'] = whole_car_lod(car)
        if record.get('dead') or entity_id == me_in or record.get('key') in driven:
            continue
        lift_sunk_car(car, record)
    return True


def whole_car_lod(car):
    """The game's far steps for a car (models' lod_config 7000 / 10000):
    its middle step had no material here - a black car, or only its wheels.
    The car is drawn whole until it is not drawn at all."""
    try:
        assemble = car.gameObject.GetComponent('VehiclePhysicAssemble')
        models = [getattr(assemble, 'model', None)] + list(getattr(assemble, 'models', None) or []) \
            + list(getattr(assemble, 'brokenWheelModels', None) or [])
    except Exception:
        return False
    models = [model for model in models if model is not None]
    if len(models) < 2:
        return False                            # not made yet: next time
    try:
        for model in models:
            model.lod_config = CAR_LOD
    except Exception:
        if once('car-lod'):
            log_error('local-battle-car-lod-error')
        return False
    return True


def lift_sunk_car(car, record):
    """A car that fell through the ground (out of it while it rolled, a
    wreck) is put back on it where it is, or where it last stood."""
    try:
        point, yaw = car_pose(car)
        assemble = car.gameObject.GetComponent('VehiclePhysicAssemble')
        if assemble is not None and getattr(assemble, 'vehicle', None) is not None:
            point = _point(assemble.vehicle.position)
    except Exception:
        return False
    floor = surface_below(point[0], point[2], point[1] + CAR_SINK_PROBE)
    if floor is not None and point[1] >= floor - CAR_SINK:
        record['stood'] = (point[0], point[1], point[2], yaw)
        return False
    if floor is None:
        stood = record.get('stood')
        if stood is None or point[1] >= stood[1] - CAR_SINK_PROBE / 4.0:
            return False                        # the ground here is not loaded: nothing to tell
        floor = surface_below(stood[0], stood[2], stood[1] + CAR_SINK_PROBE)
        if floor is None:
            floor = stood[1]
        point = stood
    target = (point[0], floor + VEHICLE_LIFT, point[2])
    if not place_car_physics(car, target, yaw):
        return False
    hold_entity(car, target, yaw)
    log('local-battle-car-lifted', vehicle=car.id, key=record.get('key'), was=round(point[1]), to=round(floor))
    return True


def prepare_new_vehicles():
    for entity_id, record in _vehicles.items():
        if record.get('prepared'):
            continue
        car = vehicle_entity(entity_id)
        if car is None or not getattr(car, 'inworld', False):
            continue
        record['prepared'] = prepare_vehicle(car)


def client_filter(car):
    try:
        import BigWorld
        if type(getattr(car, 'filter', None)).__name__ != 'DumbFilter':
            car.filter = BigWorld.DumbFilter()
        return True
    except Exception:
        if once('vehicle-filter'):
            log_error('local-battle-vehicle-filter-error')
        return False


def vehicle_has_nos(tps):
    """A car's nitro lasts NOS_DURATION seconds; 0 (the tuk-tuk, the
    truck, the boat) is a car without one."""
    try:
        return float(getattr(_properties_module().getVehicleData(int(tps)), 'NOS_DURATION', 0.0) or 0.0) > 0.0
    except Exception:
        return True


def prepare_vehicle(car):
    if car is None:
        return False
    client_filter(car)
    car.vHasHp = 1
    try:
        # LandCar.__init__ gave every car (isCarryVehicle False) the nitro
        # button; on one without nitro it did nothing
        car.supportNos = vehicle_has_nos(getattr(car, 'tpsVehicleID', 0))
    except Exception:
        if once('vehicle-nos'):
            log_error('local-battle-vehicle-nos-error')
    try:
        buffs = car.vehicleBuff
        for name in VEHICLE_BUFFS:
            if not buffs[name]:
                buffs[name] = 1.0
    except Exception:
        if once('vehicle-buff'):
            log_error('local-battle-vehicle-buff-error')
    try:
        top = float(car.maxSpeed or 0.0)
        if top and not getattr(car, 'topSpeedClient', 0.0):
            car.topSpeedClient = top
        if top and not getattr(car, 'basicMaxSpeed', 0.0):
            car.basicMaxSpeed = top
    except Exception:
        if once('vehicle-top-speed'):
            log_error('local-battle-vehicle-speed-error')
    try:
        camp = car.campType
        inner = getattr(camp, 'fixedDict', None)
        if inner is not None:
            inner['camp'] = VEHICLE_CAMP
        camp['camp'] = VEHICLE_CAMP
    except Exception:
        if once('vehicle-camp'):
            log_error('local-battle-vehicle-camp-error')
    return True


def place_vehicles(count=VEHICLE_COUNT, randomizer=None):
    if BATTLE['phase'] != 'fighting':
        return 0
    import random
    randomizer = randomizer or random.Random(match_uuid() + '-vehicles')
    spawn = BATTLE['spawn'] or (0.0, 0.0, 0.0)
    placed = []
    for _try in range(VEHICLE_TRIES * count):
        if len(placed) >= count:
            break
        angle = randomizer.uniform(0.0, 2.0 * math.pi)
        distance = randomizer.uniform(VEHICLE_MIN_RADIUS, VEHICLE_RADIUS)
        x = spawn[0] + distance * math.sin(angle)
        z = spawn[2] + distance * math.cos(angle)
        if any(math.hypot(x - px, z - pz) < VEHICLE_SPACING for px, pz in placed):
            continue
        ground = surface_clear(x, z)
        if ground is None:
            continue
        class_name, land, tps = VEHICLE_FLEET[len(placed) % len(VEHICLE_FLEET)]
        if spawn_own_car(class_name, land, tps, x, z, ground, randomizer.uniform(-math.pi, math.pi)) is not None:
            placed.append((x, z))
    log('local-battle-vehicles', placed=len(placed))
    return len(placed)


def vehicle_entity(entity_id):
    try:
        import BigWorld
        return BigWorld.entities.get(entity_id)
    except Exception:
        return None


def nearest_vehicle(player, position):
    best, best_distance = None, VEHICLE_ENTER_RANGE
    for entity_id, record in _vehicles.items():
        car = vehicle_entity(entity_id)
        if car is None or record.get('dead'):
            continue
        try:
            distance = math.hypot(car.position.x - position.x, car.position.z - position.z)
        except Exception:
            continue
        if distance <= best_distance:
            best, best_distance = entity_id, distance
    return best


def watch_vehicles(player):
    if _heritages:
        fill_heritages()
    if player is None or not _vehicles:
        return
    prepare_new_vehicles()
    now = time.time()
    if now - _car_care['at'] >= CAR_CARE_EVERY:
        _car_care['at'] = now
        car_care(player)
    try:
        position = player.position
        seated = bool(getattr(player, 'inLandVehicle', False))
    except Exception:
        return
    if seated and getattr(player, 'isLandDriver', False):
        keep_upright(vehicle_entity(getattr(player, 'vehicleEntID', 0)))
    target = None if seated else nearest_vehicle(player, position)
    for entity_id, record in list(_vehicles.items()):
        near = entity_id == target
        if near == record['near']:
            continue
        car = vehicle_entity(entity_id)
        record['near'] = near
        if car is None:
            continue
        try:
            others = [avatar for avatar in list(car.inRangeAvts or []) if avatar != player.id]
            car.inRangeAvts = others + ([player.id] if near else [])
            if near:
                car.onTarget()
            else:
                car.onCancleTarget()
        except Exception:
            if once('vehicle-near'):
                log_error('local-battle-vehicle-near-error')


def install_tilt_floor():
    cls = getattr(sys.modules.get(VEHICLE_CONTROLLER_MODULE), VEHICLE_CONTROLLER, None)
    if not isinstance(cls, type):
        return False
    if cls.__dict__.get('_rl_tilt_floor'):
        return True

    def get_tilt(self, _floor=VEHICLE_MAX_TILT):
        return max(float(self.__dict__.get('_rl_max_tilt', 0.0) or 0.0), _floor)

    def set_tilt(self, value):
        self.__dict__['_rl_max_tilt'] = value

    try:
        cls.maxTiltAngle = property(get_tilt, set_tilt)
        cls._rl_tilt_floor = True
    except Exception:
        log_error('local-battle-vehicle-tilt-floor-error')
        return False
    return True


def keep_upright(car):
    try:
        controller = car.gameObject.GetComponent(VEHICLE_CONTROLLER)
    except Exception:
        return False
    if controller is None:
        return False
    try:
        if float(getattr(controller, 'maxTiltAngle', 0.0) or 0.0) < VEHICLE_MAX_TILT:
            controller.maxTiltAngle = VEHICLE_MAX_TILT
            return True
    except Exception:
        if once('vehicle-tilt'):
            log_error('local-battle-vehicle-tilt-error')
    return False


def set_seats(car, seats):
    old = list(car.usedHangSockets or [])
    car.usedHangSockets = seats
    changed = getattr(car, 'set_usedHangSockets', None)
    if callable(changed):
        changed(old)


def set_flag(car, name, value):
    old = getattr(car, name, None)
    setattr(car, name, value)
    changed = getattr(car, 'set_' + name, None)
    if callable(changed):
        changed(old)


CAR_PITCH_SOFT = 32.0                   # degrees: nose up / down past this and still rising - held
CAR_ROLL_SOFT = 38.0                    # degrees: on its side past this and still rolling - held
_steady = {}                            # car id -> (pitch, roll) a frame ago


def steady_my_car():
    """Up a steep hill the engine's climbing force (getDriveForce adds the
    car's weight times the slope) lifted the front wheels and turned the car
    over backwards.  Past a soft limit, while it still tips further, its
    turning that way is taken out - the ground and gravity bring it back;
    a car on its wheels is never touched."""
    player = current_player()
    if player is None or not getattr(player, 'isLandDriver', False):
        _steady.clear()
        return False
    car = vehicle_entity(getattr(player, 'vehicleEntID', 0))
    engine = vehicle_engine(car) if car is not None else None
    vehicle = getattr(engine, '_vehicle', None)
    if vehicle is None:
        return False
    pitch, roll = car_tilt(car)
    last = _steady.get(car.id)
    _steady.clear()
    _steady[car.id] = (pitch, roll)
    if last is None:
        return False
    try:
        transform = car.gameObject.transform
        axes = []
        if abs(pitch) > CAR_PITCH_SOFT and abs(pitch) > abs(last[0]):
            axes.append(_point(transform.right))
        if abs(roll) > CAR_ROLL_SOFT and abs(roll) > abs(last[1]):
            axes.append(_point(transform.forward))
        if not axes:
            return False
        spin = _point(vehicle.angular_velocity)
        for axis in axes:
            along = sum(a * b for a, b in zip(spin, axis))
            spin = tuple(a - b * along for a, b in zip(spin, axis))
        import math3d
        vehicle.angular_velocity = math3d.vector(spin[0], spin[1], spin[2])
    except Exception:
        if once('steady-car'):
            log_error('local-battle-steady-car-error')
        return False
    return True


DRIVE_SAMPLE_EVERY = 0.1
DRIVE_SAMPLES = 60
DRIVE_FIELDS = ('speed', 'gear', 'rpm', 'soundRpm', 'throttle', 'nosOpen', '_engineEnable', '_drivingState',
                '_acc', '_brk')


def record_drive(car_id, left=DRIVE_SAMPLES, rows=None):
    """The engine's numbers every tenth of a second for the first seconds
    of a drive (the engine sound stuttered: which of them jumps)."""
    rows = [] if rows is None else rows
    car = vehicle_entity(car_id)
    engine = vehicle_engine(car) if car is not None else None
    me = current_player()
    if engine is None or me is None or getattr(me, 'vehicleEntID', 0) != car_id:
        left = 0
    else:
        row = []
        for field in DRIVE_FIELDS:
            value = getattr(engine, field, None)
            row.append(round(value, 2) if isinstance(value, float) else value if isinstance(value, (int, bool)) else None)
        rows.append(row)
    if left > 1:
        call_later(DRIVE_SAMPLE_EVERY, record_drive, car_id, left - 1, rows)
        return True
    if rows:
        log('local-battle-drive-samples', vehicle=car_id, fields=list(DRIVE_FIELDS), rows=rows,
            nos=bool(getattr(car, 'supportNos', False)) if car is not None else None)
    return False


def take_control(player, car):
    call_later(1.0, record_drive, car.id)
    key = _vehicles.get(car.id, {}).get('key')
    if key in _car_motion:
        _car_motion.pop(key, None)              # ours to drive now, not where another window put it
        if key in _engines:
            engine_running(car, key, False)
    install_tilt_floor()
    run_motion()                                # steady_my_car runs with the frames
    client_filter(car)
    if not stop_coast(car):
        car.selectControl(True)
    car.onControlledBy(player.id, False)
    set_flag(car, 'hasDriver', 1)


def release_control(player, car):
    set_flag(car, 'hasDriver', 0)
    start_coast(player, car)


def vehicle_engine(car):
    try:
        controller = car.gameObject.GetComponent(VEHICLE_CONTROLLER)
        return controller.veng if controller is not None else None
    except Exception:
        return None


def vehicle_speed(car):
    try:
        return abs(float(vehicle_engine(car)._vehicle.get_speed_kmh()))
    except Exception:
        return 0.0


def start_coast(player, car):
    record = _vehicles.setdefault(car.id, {})
    engine = vehicle_engine(car)
    if engine is not None:
        try:
            record['idle_brake'] = engine.idle_brake_force
            engine.idle_brake_force = 0
            engine.unhandBrake()
        except Exception:
            if once('vehicle-coast-brake'):
                log_error('local-battle-vehicle-coast-error')
    record['coast'] = time.time()
    record['coast_at'] = None
    call_later(VEHICLE_COAST_POLL, coast, player.id, car.id)


def stop_coast(car):
    record = _vehicles.get(car.id, {})
    if record.get('coast') is None:
        return False
    record['coast'] = None
    engine = vehicle_engine(car)
    if engine is not None and 'idle_brake' in record:
        try:
            engine.idle_brake_force = record.pop('idle_brake')
        except Exception:
            pass
    return True


def coast(player_id, entity_id):
    record = _vehicles.get(entity_id, {})
    started = record.get('coast')
    car = vehicle_entity(entity_id)
    if started is None or car is None:
        return False
    if record.get('dead'):
        record['coast'] = None
        return False
    if still_rolling(record, car) and time.time() - started < VEHICLE_COAST_LIMIT:
        call_later(VEHICLE_COAST_POLL, coast, player_id, entity_id)
        return True
    park(player_id, car)
    return False


VEHICLE_ROLL_SPEED = 20.0               # units/s: slower than this, a car left rolling has stopped


def still_rolling(record, car):
    """Out of the car, its engine (the driver's controller) is gone and
    read 0 km/h at once: it was parked a quarter second after a rush exit
    while it still rolled on here - the others saw it stop dead.  How far
    it went since the last look tells."""
    point, _yaw = car_pose(car)
    last, record['coast_at'] = record.get('coast_at'), point
    if last is None:
        return True
    moved = math.hypot(point[0] - last[0], point[2] - last[2])
    if lift_sunk_car(car, record):
        return False                            # it fell through: put back, and it stops there
    return moved / VEHICLE_COAST_POLL > VEHICLE_ROLL_SPEED or vehicle_speed(car) > VEHICLE_PARK_SPEED


def park(player_id, car):
    stop_coast(car)
    _vehicles.setdefault(car.id, {})['parked_at'] = time.time()
    try:
        car.onUncontrolledBy(player_id)
        car.selectControl(False)
    except Exception:
        log_error('local-battle-vehicle-park-error', vehicle=car.id)
        return False
    log('local-battle-vehicle-parked', vehicle=car.id)
    return True


def refresh_seats(car):
    for name in ('pullAvatarSocketInfo', 'refreshHintUI'):
        function = getattr(car, name, None)
        if callable(function):
            try:
                function()
            except Exception:
                if once('vehicle-' + name):
                    log_error('local-battle-vehicle-refresh-error', step=name)


def seat_player(player, car, socket):
    driver = socket == VEHICLE_DRIVER_SOCKET
    boarding = not (getattr(player, 'inLandVehicle', False) and getattr(player, 'vehicleEntID', 0) == car.id)
    was_driver = (not boarding) and bool(getattr(player, 'isLandDriver', False))
    if was_driver and not driver:
        release_control(player, car)
    player.inLandVehicle = True
    player.isLandDriver = driver
    player.isDriver = int(driver)
    player.vehicleEntID = car.id
    player.hangSockName = socket
    player.sockNameOnCar = socket
    seats = [seat for seat in list(car.usedHangSockets or []) if seat.get('id') != player.id]
    set_seats(car, seats + [{'sockname': socket, 'id': player.id}])
    if boarding:
        car.onGetOn(player.id)
    if driver and not was_driver:
        take_control(player, car)
    player.refreshDriveState(car.id)
    refresh_seats(car)
    show_vehicle_hp(car)
    _vehicles.get(car.id, {})['near'] = False


def show_vehicle_hp(car):
    try:
        car.onRecoverHP(int(car.hp))
        return True
    except Exception:
        if once('vehicle-hp-ui'):
            log_error('local-battle-vehicle-hp-ui-error')
        return False


def clear_seat(player):
    player.inLandVehicle = False
    player.isLandDriver = False
    player.isDriver = 0
    player.vehicleEntID = 0
    player.hangSockName = ''
    player.sockNameOnCar = ''


def seat_taken(car, socket, player_id=None):
    return any(seat.get('sockname') == socket and seat.get('id') != player_id
               for seat in list(car.usedHangSockets or []))


def free_passenger_socket(car):
    for socket in list(car.totalSockets or []):
        if socket != VEHICLE_DRIVER_SOCKET and not seat_taken(car, socket):
            return socket
    return None


def on_get_on_driver(player, vehicle_id=0, *_args, **_kwargs):
    call_later(WEAPON_SWITCH_DELAY, get_on, player, vehicle_id, True)
    return None


def on_get_on_passenger(player, vehicle_id=0, *_args, **_kwargs):
    call_later(WEAPON_SWITCH_DELAY, get_on, player, vehicle_id, False)
    return None


def get_on(player, vehicle_id, driver):
    car = vehicle_entity(vehicle_id)
    if car is None or getattr(player, 'inLandVehicle', False):
        return False
    record = _vehicles.get(vehicle_id, {})
    if record.get('dead'):
        return False
    wait = record.get('left_at', 0.0) + VEHICLE_REBOARD_DELAY - time.time()
    if wait > 0.0:
        call_later(wait, get_on, player, vehicle_id, driver)
        return False
    prepare_vehicle(car)
    socket = None
    try:
        if driver and seat_taken(car, VEHICLE_DRIVER_SOCKET):
            driver = False
        socket = VEHICLE_DRIVER_SOCKET if driver else free_passenger_socket(car)
        if socket is None:
            tip_text('No free seat')
            return False
        seat_player(player, car, socket)
    except Exception:
        log_error('local-battle-get-on-error', vehicle=vehicle_id, driver=driver)
        clear_seat(player)
        return False
    _round['vehicle'] = True            # the Activity task "Use a vehicle once"
    log('local-battle-get-on', vehicle=vehicle_id, driver=driver, seat=socket)
    return True


def on_switch_seat(player, seat=0, *_args, **_kwargs):
    try:
        seat = int(seat)
    except Exception:
        return None
    call_later(WEAPON_SWITCH_DELAY, switch_seat, player, seat)
    return None


def switch_seat(player, seat):
    car = vehicle_entity(getattr(player, 'vehicleEntID', 0))
    if car is None or not getattr(player, 'inLandVehicle', False):
        return False
    sockets = list(car.totalSockets or [])
    if not 0 <= seat < len(sockets):
        return False
    socket = sockets[seat]
    if socket == getattr(player, 'hangSockName', None):
        return False
    if seat_taken(car, socket, player.id):
        tip_text('Seat taken')
        return False
    try:
        seat_player(player, car, socket)
    except Exception:
        log_error('local-battle-switch-seat-error', seat=seat)
        return False
    log('local-battle-switch-seat', vehicle=car.id, seat=socket)
    return True


def on_get_off_vehicle(player, vehicle_id=0, *_args, **_kwargs):
    call_later(WEAPON_SWITCH_DELAY, get_off, player, vehicle_id)
    return None


def get_off(player, vehicle_id):
    car = vehicle_entity(vehicle_id or getattr(player, 'vehicleEntID', 0))
    if car is None:
        return False
    was_driver = bool(getattr(player, 'isLandDriver', False))
    landing = exit_point(car, getattr(player, 'hangSockName', ''))
    try:
        set_seats(car, [seat for seat in list(car.usedHangSockets or []) if seat.get('id') != player.id])
        clear_seat(player)
        if was_driver:
            release_control(player, car)
        car.onGetOff(player.id)
        player.onSwitchToOffVehicle()
    except Exception:
        log_error('local-battle-get-off-error', vehicle=vehicle_id)
        return False
    _vehicles.get(car.id, {})['left_at'] = time.time()
    if landing is not None:
        call_later(VEHICLE_EXIT_DELAY, land_player, player, landing)
    log('local-battle-get-off', vehicle=car.id, driver=was_driver)
    return True


def surface_below(x, z, top):
    physics_module = sys.modules.get('libclaudia.Classes.Physics')
    ray_module = sys.modules.get('libclaudia.Classes.Ray')
    if physics_module is not None and ray_module is not None:
        try:
            hit = ray_module.RaycastHit()
            if physics_module.Physics.RaycastWithScene(physics_module.Vector3(x, top, z),
                                                       physics_module.Vector3(0.0, -1.0, 0.0), hit,
                                                       VEHICLE_EXIT_PROBE * 3.0):
                return top - float(hit.distance)
        except Exception:
            pass
    return ground_height(x, z) or None


def exit_point(car, socket):
    try:
        transform = car.gameObject.transform
        x, y, z = _point(transform.position)
        right = _point(transform.right)
    except Exception:
        return None
    side = -1.0 if socket == VEHICLE_DRIVER_SOCKET else 1.0
    flat = math.hypot(right[0], right[2]) or 1.0
    x += side * right[0] / flat * VEHICLE_EXIT_SIDE
    z += side * right[2] / flat * VEHICLE_EXIT_SIDE
    surface = surface_below(x, z, y + VEHICLE_EXIT_PROBE)
    return (x, (surface if surface is not None else y) + VEHICLE_EXIT_LIFT, z)


def land_player(player, point):
    try:
        player.onTeleport(player.spaceID, point, (0.0, 0.0, float(getattr(player, 'yaw', 0.0) or 0.0)))
        return True
    except Exception:
        if once('vehicle-exit-place'):
            log_error('local-battle-vehicle-exit-error')
        return False


def bullet_damage(weapon_id, rail_id):
    module = _properties_module()
    try:
        rail = module.getGunRailData(int(rail_id or weapon_id))
        return float(module.getGunBulletData(int(rail.BULLET_ID)).DAMAGE)
    except Exception:
        return VEHICLE_DEFAULT_DAMAGE


# Bows and crossbows (iDtsFlyBullet): the arrow flies on this client; the
# shot is announced with cell.broadcastCreateBowBullet(pos, dir, bulletID,
# weaponID, railID, motorID, ...) - for the others to see it, the server
# never echoed it back (the echo made the client build the arrow again and
# fail) - and where it ends with cell.dtsFlyBulletHit(entityID, hitScene,
# hitPos, hitPart, ...).  A hit on a body is a gun hit with the bow's own
# bullet (DAMAGE, PARTS_DAMAGE_FACTORS).
_bow = {}


def on_bow_shot(player, src_pos=None, direction=None, bullet_id=0, weapon_id=0, rail_id=0, *_args, **_kwargs):
    try:
        _bow.update(src=_point(src_pos) if src_pos is not None else None, weapon=int(weapon_id or 0),
                    rail=int(rail_id or weapon_id or 0), bullet=int(bullet_id or 0))
    except Exception:
        if once('bow-shot'):
            log_error('local-battle-bow-shot-error')
    count_stat('fired')
    count_weapon(_bow.get('weapon') or _bow.get('rail'), 'fired')
    return None


def on_fly_bullet_hit(player, entity_id=0, hit_scene=True, hit_pos=None, hit_part=0, *_args, **_kwargs):
    try:
        entity_id = int(entity_id or 0)
    except Exception:
        return None
    if not entity_id:
        return None                             # the ground or a wall: the arrow just sticks there
    rail = _bow.get('rail') or 0
    info = {'weaponID': _bow.get('weapon') or rail, 'railID': rail}
    src = _bow.get('src') or _point(player.position)
    if entity_id in _vehicles:
        damage_vehicle(player, entity_id, bullet_damage(info['weaponID'], rail), src, HIT_SHOOT, hit_part,
                       weapon_record(info['weaponID'], rail, HIT_SHOOT), hit_pos)
        return None
    target = remote_avatar(entity_id)
    if target is not None:
        shoot_avatar(player, target, info, src, hit_part, hit_pos)
        log('local-battle-bow-hit', target=entity_id, part=int(hit_part or 0), rail=rail)
    return None


def on_shoot_hit(player, info=None, src_pos=None, entity_id=0, hit_part=0, hit_pos=None, *_args, **_kwargs):
    try:
        entity_id = int(entity_id)
    except Exception:
        return None
    info = info if isinstance(info, dict) else {}
    if entity_id not in _vehicles:
        target = remote_avatar(entity_id)
        if target is not None:
            shoot_avatar(player, target, info, src_pos, hit_part, hit_pos)
        return None
    weapon = info.get('weaponID', 0)
    damage = bullet_damage(weapon, info.get('railID', 0))
    weapon_info = {'weaponID': weapon, 'railID': info.get('railID', weapon), 'hitType': info.get('hitType', 1),
                   'stateID': info.get('stateID', 0), 'appearanceID': 0, 'suitID': 0}
    damage_vehicle(player, entity_id, damage, src_pos, info.get('hitType', 1), hit_part, weapon_info, hit_pos)
    return None


def broadcast(car, name, args):
    function = getattr(car, name, None)
    if not callable(function):
        return False
    try:
        function(*args)
        return True
    except Exception:
        if once('vehicle-broadcast-' + name):
            log_error('local-battle-vehicle-broadcast-error', call=name)
        return False


def show_damage_text(where, damage, hit_type, hit_part):
    physics_module = sys.modules.get('libclaudia.Classes.Physics')
    try:
        import Globals
        comp = Globals.uiMgr.UIBattlegroundsInGame.gameObject.GetComponent(DAMAGE_TEXT_COMP)
        x, y, z = _point(where)
        comp.showDamageText(physics_module.Vector3(x, y, z), int(round(damage)), hit_type, hit_part, True, False)
        return True
    except Exception:
        if once('vehicle-damage-text'):
            log_error('local-battle-vehicle-damage-text-error')
        return False


def damage_vehicle(player, entity_id, damage, src_pos, hit_type, hit_part, weapon, hit_pos=None, relayed=False):
    record = _vehicles.get(entity_id)
    car = vehicle_entity(entity_id)
    if car is None or record is None or record.get('dead'):
        return None
    try:
        old = int(car.hp)
    except Exception:
        return None
    new = max(0, old - int(round(damage)))
    car.hp = new
    if not relayed and record.get('key'):
        # the others take the same off their copy (each window adds up every hit)
        emit('car_hit', {'key': record['key'], 'dmg': int(round(damage)), 'ht': int(hit_type or HIT_SHOOT),
                         'part': int(hit_part or 0), 'src': relay_point(src_pos)})
    if not broadcast(car, 'damage', (player.id, src_pos, weapon, int(round(damage)), new, hit_part, hit_type)):
        if hit_pos is None:
            x, y, z = _point(car.position)
            hit_pos = (x, y + DAMAGE_TEXT_LIFT, z)
        show_damage_text(hit_pos, damage, hit_type, hit_part)
        try:
            car.onDamage(src_pos, player.id, damage, new, hit_type, hit_part, weapon)
        except Exception:
            if once('vehicle-damage'):
                log_error('local-battle-vehicle-damage-error', vehicle=entity_id)
    if new <= 0:
        explode_vehicle(player, car, src_pos, weapon, hit_part, hit_type, relayed)
    return new


def relay_point(point):
    try:
        return [round(value, 2) for value in _point(point)] if point is not None else None
    except Exception:
        return None


def explode_vehicle(player, car, src_pos, weapon, hit_part, hit_type, relayed=False):
    record = _vehicles.get(car.id)
    if record is not None:
        record['dead'] = True
        record['near'] = False
        key = record.get('key')
        if not relayed and key:
            emit('car_die', {'key': key, 'ht': int(hit_type or HIT_SHOOT), 'part': int(hit_part or 0),
                             'src': relay_point(src_pos)})
        if key is not None:
            _car_motion.pop(key, None)          # a wreck: nobody drives it any more
            if key in _engines:
                engine_running(car, key, False)
    me = current_player()
    if me is not None and getattr(me, 'vehicleEntID', 0) == car.id and getattr(me, 'inLandVehicle', False):
        get_off(me, car.id)
    try:
        car.onCancleTarget()
        car.inRangeAvts = []
    except Exception:
        pass
    if not broadcast(car, 'die', (player.id, src_pos, weapon, hit_part, hit_type)):
        try:
            car.onDie(src_pos, player.id, weapon, hit_part, hit_type)
        except Exception:
            log_error('local-battle-vehicle-die-error', vehicle=car.id)
            return False
    log('local-battle-vehicle-destroyed', vehicle=car.id, land=record.get('land') if record else None)
    return True


PART_INDEX = {1: 0, 2: 1, 3: 2, 4: 3, 7: 3, 8: 3, 9: 3, 5: 4, 6: 4, 10: 4, 11: 4}
HEAD_PART = 1
CHEST_PART = 2
HIT_SHOOT = 1
HIT_EXPLODE = 4
KILL_TEXT = 'I_DTS_SHOOT_KILL'
KILL_TEXT_HEAD = 'I_DTS_SHOOT_HEAD_KILL'
MY_KILL_TEXT = 'I_DTS_I_SHOOT_KILL'
KILL_TEXT_FALLBACK = '%s used %s to kill %s'
MY_KILL_TEXT_FALLBACK = 'You used %s to kill %s'
SELF_MIN_HP = 0
BODY_LINGER = 3.0
_dead = set()
_buried = set()


def remote_bodies():
    bodies = []
    for battle_id, handle in list(_remote.items()):
        entity = _resolve_entity(handle)
        if entity is not None and hasattr(entity, 'position'):
            bodies.append((battle_id, entity))
    return bodies


def remote_avatar(entity_id):
    if entity_id in _dead:
        return None
    for _battle_id, entity in remote_bodies():
        if getattr(entity, 'id', None) == entity_id:
            return entity
    return None


def battle_id_of(entity):
    for battle_id, known in remote_bodies():
        if known is entity:
            return battle_id
    return None


def rail_bullet(rail_id):
    module = _properties_module()
    try:
        rail = module.getGunRailData(int(rail_id))
        return rail, module.getGunBulletData(int(rail.BULLET_ID))
    except Exception:
        return None, None


def gun_damage(rail_id, hit_part, distance_to_target):
    rail, bullet = rail_bullet(rail_id)
    if bullet is None:
        return VEHICLE_DEFAULT_DAMAGE
    damage = float(getattr(bullet, 'DAMAGE', VEHICLE_DEFAULT_DAMAGE) or VEHICLE_DEFAULT_DAMAGE)
    factors = list(getattr(bullet, 'PARTS_DAMAGE_FACTORS', None) or [])
    index = PART_INDEX.get(int(hit_part or 0), 1)
    if index < len(factors):
        damage *= float(factors[index])
    reaches = list(getattr(rail, 'BULLET_DECAY_DISTANCE', None) or [])
    falloff = list(getattr(rail, 'BULLET_DECAY_FACTOR', None) or [])
    for reach, factor in zip(reaches, falloff):
        if distance_to_target <= reach:
            damage *= float(factor)
            break
    return max(1.0, damage)


def held_weapon_name(player):
    try:
        slot = int(getattr(player, 'dtsCurWeapon', MELEE_SLOT))
        value = getattr(player, 'dtsWeapon%d' % slot)
        item = int(value['weaponID']) if hasattr(value, 'keys') else int(value or 0)
        return prop_name(item) if item else 'Fist'
    except Exception:
        return 'Gun'


def count_stat(name, amount=1):
    """Match statistics for the profile's STATS page."""
    _round[name] = _round.get(name, 0) + amount


def count_weapon(weapon, field, amount=1):
    """Per-weapon match totals (kills, damage, hits, fired by gun ID): the
    lobby adds them to the saved weaponStats, which the Meet page's weapon
    proficiency and best-weapon title are computed from.  ``weapon`` is a
    weapon record ({'weaponID': ...}) or a gun ID; fists (0) are not a weapon."""
    try:
        gun = int(weapon.get('weaponID') or 0) if hasattr(weapon, 'get') else int(weapon or 0)
        amount = int(amount)
    except Exception:
        return False
    if gun <= 0 or amount <= 0:
        return False
    entry = _round.setdefault('weapons', {}).setdefault(str(gun), {})
    entry[field] = entry.get(field, 0) + amount
    return True


def held_gun(player):
    """The gun ID in the hand now (0: fists or unknown)."""
    try:
        slot = int(getattr(player, 'dtsCurWeapon', MELEE_SLOT))
        value = getattr(player, 'dtsWeapon%d' % slot)
        return int(value['weaponID'] or 0) if hasattr(value, 'keys') else int(value or 0)
    except Exception:
        return 0


def on_fire(player, *_args, **_kwargs):
    count_stat('fired')
    count_weapon(held_gun(player), 'fired')
    return None


def shoot_avatar(player, target, info, src_pos, hit_part, hit_pos):
    count_stat('hits')
    count_weapon(info.get('weaponID') or info.get('railID'), 'hits')
    if int(hit_part or 0) == HEAD_PART:
        count_stat('headshots')
    rail_id = info.get('railID') or info.get('weaponID') or 0
    reach = distance(_point(src_pos), _point(hit_pos if hit_pos is not None else target.position))
    damage = gun_damage(rail_id, hit_part, reach)
    hit_type = HIT_SHOOT
    weapon = weapon_record(info.get('weaponID', 0), rail_id, hit_type, info.get('stateID', 0))
    return hurt_avatar(player, target, damage, src_pos, hit_part, hit_type, weapon, held_weapon_name(player))


def weapon_record(weapon_id, rail_id, hit_type, state_id=0):
    return {'weaponID': int(weapon_id or 0), 'railID': int(rail_id or weapon_id or 0), 'hitType': hit_type,
            'stateID': int(state_id or 0), 'appearanceID': 0, 'suitID': 0}


def hurt_avatar(player, target, damage, src_pos, hit_part, hit_type, weapon, weapon_name):
    if getattr(target, 'id', None) in _dead:
        return None
    if is_player_body(target):
        return hit_player(player, target, damage, src_pos, hit_part, hit_type, weapon, weapon_name)
    try:
        old = int(target.hp)
    except Exception:
        old = FULL_HP
    amount = int(round(damage))
    new = max(0, old - amount)
    target.hp = new
    count_stat('damage', old - new)
    count_weapon(weapon, 'damage', old - new)
    if not broadcast(target, 'damage', (player.id, src_pos, weapon, amount, new, hit_part, hit_type)):
        show_damage_text(target.position, amount, hit_type, hit_part)
    if new <= 0:
        kill_avatar(player, target, src_pos, weapon, hit_part, hit_type, weapon_name)
    return new


def kill_avatar(player, target, src_pos, weapon, hit_part, hit_type, weapon_name):
    _dead.add(target.id)
    count_weapon(weapon, 'kills')
    try:
        reach = distance(_point(src_pos), _point(target.position))
        _round['max_kill_dis'] = max(_round.get('max_kill_dis', 0.0), reach)
    except Exception:
        pass
    if not broadcast(target, 'die', (player.id, src_pos, weapon, hit_part, hit_type)):
        try:
            target.onDie(src_pos, player.id, weapon, hit_part, hit_type)
        except Exception:
            log_error('local-battle-kill-error', target=target.id)
    battle_id = battle_id_of(target)
    if battle_id is not None:
        send(KILL_PREFIX + json.dumps({'id': BATTLE['entity_id'], 'target': battle_id,
                                       'weapon': str(weapon_name or '')}))
    announce_kill(player, target, weapon_name, int(hit_part or 0) == HEAD_PART)
    if battle_id is not None:
        call_later(BODY_LINGER, bury_body, battle_id)
    log('local-battle-kill', target=target.id, name=avatar_name(target), weapon=weapon_name)
    return True


# --------------------------------------------------------------------------
# Other players, smoothly.  Positions come 20 times a second; drawn as they
# came they stepped (the other window looked like 5 fps).  Each body is shown
# a little in the past (MOTION_DELAY), between the two positions around that
# moment, every frame.  Their pose, fall phase, lean, guns and plane come
# with every position (my_act / apply_act) and their look with the join
# (my_look / look_properties).
# --------------------------------------------------------------------------

MOTION_DELAY = 0.12
MOTION_KEEP = 8
MOTION_SNAP = 600.0                     # further than this between two samples: a teleport, no gliding
_motion = {'bodies': {}, 'driver': None}
_acts = {}


def push_motion(battle_id, handle, position, yaw):
    now = time.time()
    body = _motion['bodies'].get(battle_id)
    point = _point(position)
    yaw = float(yaw or 0.0)
    if body is None:
        _motion['bodies'][battle_id] = {'handle': handle, 'samples': [(now, point, yaw)]}
        hold_entity(handle, point, yaw)
    else:
        body['handle'] = handle
        samples = body['samples']
        if distance(samples[-1][1], point) > MOTION_SNAP:
            del samples[:]                      # teleported: no gliding across the map
        samples.append((now, point, yaw))
        del samples[:-MOTION_KEEP]
    run_motion()
    return True


def run_motion():
    token = BATTLE.get('entity_id')
    if _motion['driver'] == token:
        return True
    _motion['driver'] = token
    try:
        current_player().behaviour.StartCoroutine(motion_frames(token))
        return True
    except Exception:
        _motion['driver'] = None
        if once('motion-coroutine'):
            log_error('local-battle-motion-coroutine-error')
        return False


def motion_frames(token):
    while BATTLE.get('phase') == 'fighting' and BATTLE.get('entity_id') == token:
        yield None
        perf_frame()
        try:
            step_motion(time.time())
        except Exception:
            if once('motion-step'):
                log_error('local-battle-motion-step-error')
    if _motion['driver'] == token:
        _motion['driver'] = None


def angle_lerp(first, second, share):
    turn = (second - first + math.pi) % (2.0 * math.pi) - math.pi
    return first + turn * share


def motion_point(samples, moment):
    if moment <= samples[0][0]:
        return samples[0][1], samples[0][2]
    for (t0, p0, y0), (t1, p1, y1) in zip(samples, samples[1:]):
        if t0 <= moment <= t1:
            share = (moment - t0) / (t1 - t0) if t1 > t0 else 1.0
            return tuple(a + (b - a) * share for a, b in zip(p0, p1)), angle_lerp(y0, y1, share)
    return samples[-1][1], samples[-1][2]


def motion_velocity(samples, moment):
    """How fast it moves around that moment (per second), from the two
    positions around it - standing still once the last one is reached."""
    for (t0, p0, _y0), (t1, p1, _y1) in zip(samples, samples[1:]):
        if t0 <= moment <= t1 and t1 > t0:
            return tuple((b - a) / (t1 - t0) for a, b in zip(p0, p1))
    return (0.0, 0.0, 0.0)


def step_motion(now):
    steady_my_car()
    moment = now - MOTION_DELAY
    for battle_id, body in list(_motion['bodies'].items()):
        if battle_id not in _remote:
            _motion['bodies'].pop(battle_id, None)
            continue
        entity = _resolve_entity(body['handle'])
        if entity is None or getattr(entity, 'id', None) in _dead:
            continue
        if battle_id in _seated:
            continue                            # in a car: the car carries it
        point, yaw = motion_point(body['samples'], moment)
        hold_entity(entity, point, yaw)
        set_body_velocity(entity, motion_velocity(body['samples'], moment))
    for key, glide in list(_car_motion.items()):
        car = vehicle_entity(_car_keys.get(key))
        if car is None or not glide['samples']:
            _car_motion.pop(key, None)
            continue
        if not glide.get('driven') and now - glide['samples'][-1][0] > CAR_ROLL_HOLD:
            _car_motion.pop(key, None)          # it stopped rolling: it stays there
            continue
        point, yaw = motion_point(glide['samples'], moment)
        velocity = motion_velocity(glide['samples'], moment)
        hold_entity(car, point, yaw)
        if bool(glide.get('driven')) != (key in _engines):
            engine_running(car, key, bool(glide.get('driven')))
        if place_car_physics(car, point, yaw, glide.get('tilt')):
            _past, before = motion_point(glide['samples'], moment - CAR_TURN_WINDOW)
            roll_wheels(car, key, point, yaw, velocity, turn_angle(yaw - before) / CAR_TURN_WINDOW)
        set_body_velocity(car, velocity)
    return True


CAR_ROLL_HOLD = 2.0                     # s: a car left rolling, after its last position
CAR_ROLL_AFTER = 1.0                    # s: its resting place is sent this long after it stops
CAR_ROLL_MAX = 3


def rolling_cars():
    """The cars we got out of while they still rolled (the coast after a
    rush exit): where they are, so the others see them roll on and stop
    where they stopped here."""
    now = time.time()
    rolling = []
    for car_id, record in list(_vehicles.items()):
        key = record.get('key')
        if key is None or record.get('dead'):
            continue
        if record.get('coast') is None and now - float(record.get('parked_at') or 0.0) > CAR_ROLL_AFTER:
            continue
        car = vehicle_entity(car_id)
        if car is None:
            continue
        point, yaw = car_pose(car)
        # flat: the battle host keeps an act only three levels deep (a
        # {'p': [x, y, z]} in the list lost its position on the way)
        rolling.append([key] + [round(value, 2) for value in point] + [round(yaw, 4)]
                       + [round(value, 1) for value in car_tilt(car)])
        if len(rolling) >= CAR_ROLL_MAX:
            break
    return rolling or None


def follow_rolling(rolling):
    me = current_player()
    for item in list(rolling or [])[:CAR_ROLL_MAX]:
        try:
            key, point, yaw = item[0], (float(item[1]), float(item[2]), float(item[3])), float(item[4])
        except Exception:
            continue
        car = vehicle_entity(_car_keys.get(key))
        if car is None:
            continue
        if any(seated[0] == key and seated[1] == VEHICLE_DRIVER_SOCKET for seated in _seated.values()):
            continue                            # someone drives it already
        if me is not None and getattr(me, 'vehicleEntID', 0) == car.id and getattr(me, 'isLandDriver', False):
            continue                            # we drive it
        glide = _car_motion.setdefault(key, {'samples': []})
        glide['driven'] = False
        glide['tilt'] = list(item[5:7]) if len(item) >= 7 else None
        glide['samples'].append((time.time(), point, yaw))
        del glide['samples'][:-MOTION_KEEP]
        run_motion()
    return True


CAR_TURN_WINDOW = 0.1                   # s: how fast the car turns, from its heading this long ago
CAR_STEER_MAX = 0.6                     # rad: the front wheels turn no further
CAR_STEER_SPEED = 30.0                  # slower than this, the wheels are not steered
_car_wheels = {}                        # key -> {'spin': rad, 'last': point, 'base': wheelbase}
_engines = set()                        # keys of the cars another player drives here


def turn_angle(angle):
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def roll_wheels(car, key, point, yaw, velocity, yaw_rate):
    """The wheels of a car another player drives: placing the physics car
    (resetVehiclePR) puts them straight every frame, so they slid along.
    They roll here by how far it went (wheel radius), the front ones
    steered by how fast it turns."""
    try:
        assemble = car.gameObject.GetComponent('VehiclePhysicAssemble')
        wheels = list(getattr(assemble, 'models', None) or [])
        radius = float(getattr(assemble, 'wheelRadius', 0.0) or 0.0)
    except Exception:
        return False
    if not wheels or radius <= 0.0:
        return False
    state = _car_wheels.get(key)
    if state is None:
        state = _car_wheels[key] = {'spin': 0.0, 'last': point, 'base': wheelbase(wheels)}
    last, state['last'] = state['last'], point
    ahead = (math.sin(yaw), math.cos(yaw))
    rolled = (point[0] - last[0]) * ahead[0] + (point[2] - last[2]) * ahead[1]
    state['spin'] = (state['spin'] + rolled / radius) % (2.0 * math.pi)
    speed = velocity[0] * ahead[0] + velocity[2] * ahead[1]
    steer = 0.0
    if abs(speed) >= CAR_STEER_SPEED and state['base']:
        steer = max(-CAR_STEER_MAX, min(CAR_STEER_MAX, math.atan(yaw_rate * state['base'] / speed)))
    try:
        for index, wheel in enumerate(wheels):
            if index < 2 and steer:
                wheel.rotate_y(steer)            # the front pair (boneNames: *_qian_w)
            wheel.rotate_x(state['spin'])
    except Exception:
        if once('roll-wheels'):
            log_error('local-battle-roll-wheels-error')
        return False
    return True


def wheelbase(wheels):
    try:
        front, rear = _point(wheels[0].position), _point(wheels[2].position)
        return math.hypot(front[0] - rear[0], front[2] - rear[2])
    except Exception:
        return 0.0


def engine_running(car, key, running, driver_id=0):
    """Engine sound (VehicleTPSound) and the exhaust, dust and wheel dirt
    (VehicleTPController → CarTPEffect, by the car's velocity2) of a car
    another player drives, as the old server's 'controlled by' turned on."""
    if running:
        _engines.add(key)
    else:
        _engines.discard(key)
        _car_wheels.pop(key, None)
    try:
        game_object = car.gameObject
        sound = game_object.GetComponent('VehicleTPSound')
        controller = game_object.GetComponent('VehicleTPController')
        if running:
            if sound is not None:
                sound.onBecomeControlled(driver_id)
            if controller is not None:
                controller.enabled = True
        else:
            if sound is not None:
                sound.onBecomeUncontrolled()
            if controller is not None:
                controller.onBecomeUncontrolled()
            set_body_velocity(car, (0.0, 0.0, 0.0))
    except Exception:
        if once('engine-running'):
            log_error('local-battle-engine-error', car=key)
        return False
    return True


def place_car_physics(car, point, yaw, tilt=None):
    """The car you see is the physics car (VehiclePhysicAssemble's vehicle),
    not the entity: moving the entity left it parked where it was made.
    resetVehiclePR puts the physics car, its model and the transform at a
    position and heading - every frame while another player drives it -
    tilted as the driver's is (pitch, roll in degrees: up a hill, on a
    slope; held level it floated with two wheels off the ground)."""
    pitch, roll = (float(tilt[0]), float(tilt[1])) if tilt else (0.0, 0.0)
    try:
        vector = sys.modules['libclaudia.Classes.Physics'].Vector3
        assemble = car.gameObject.GetComponent('VehiclePhysicAssemble')
        position = vector(point[0], point[1], point[2])
        if not pitch and not roll:
            assemble.resetVehiclePR(position, vector(0.0, math.degrees(yaw), 0.0))
            return True
        # resetVehiclePR reads only the heading of the angles it is given (a
        # car up a hill was drawn level, its nose in the slope): the same
        # steps with the whole rotation.
        import math3d
        rotation = math3d.euler_to_rotation(math3d.vector(math.radians(pitch), yaw, math.radians(roll)))
        neox = position.to_neox_vector()
        assemble.resetPhysicsPositionAndRotation(neox, rotation)
        assemble.resetVehicleState()
        assemble.model.position = neox
        transform = car.gameObject.transform
        transform.position = position
        transform.eulerAngles = vector(pitch, math.degrees(yaw), roll)
        return True
    except Exception:
        if once('car-physics'):
            log_error('local-battle-car-physics-error')
        return False


def set_body_velocity(entity, velocity):
    """PlayerTPAppear._updateNormal walks the body by entity.velocity (the
    animation tree's vel_x / vel_z, 'moving'); our bodies had none - they
    slid along standing."""
    vector = getattr(sys.modules.get('Math'), 'Vector3', None)
    try:
        value = vector(*velocity) if vector is not None else velocity
        entity.velocity = value
        # velocity2 is what PlayerTPAppear walks, swims, steers the parachute
        # and glides by (the engine's own did not match how the body moved:
        # the legs walked the other way - a moonwalk).
        entity.velocity2 = value
        return True
    except Exception:
        if once('body-velocity'):
            log_error('local-battle-body-velocity-error')
        return False


def weapon_id(value):
    try:
        if hasattr(value, 'keys'):
            return int(value['weaponID'] or 0)
        return int(value or 0)
    except Exception:
        return 0


def my_act():
    player = current_player()
    if player is None:
        return {}
    return {
        'p': int(getattr(player, 'pose', 0) or 0),
        'f': int(getattr(player, 'fallPhase', 0) or 0),
        'l': int(getattr(player, 'leanState', 0) or 0),
        'c': int(getattr(player, 'dtsCurWeapon', 0) or 0),
        'w': [weapon_id(getattr(player, 'dtsWeapon%d' % slot, 0)) for slot in range(BOMB_SLOT + 1)],
        'pl': 1 if _flight.get('aboard') and _flight.get('stage') == 'plane' else 0,
        'js': _jumps['start'],
        'je': _jumps['end'],
        'pt': round(float(getattr(player, 'pitch', 0.0) or 0.0), 3),
        'v': my_vehicle(player),
        'cv': rolling_cars(),
        'g': [int(getattr(player, field, 0) or 0) for field in WORN_GEAR],
    }


def apply_act(battle_id, handle, act):
    """Another player's pose, fall phase (the jump, the parachute, the
    landing), lean, guns and the one in hand - the game draws them; on the
    plane they are hidden, as everyone inside is."""
    last = _acts.get(battle_id) or {}
    entity = _resolve_entity(handle)
    if entity is None or isinstance(entity, (int, long_type)):
        return False
    hand_weapon(entity, act.get('c'), act.get('w'))
    sync_vehicle(battle_id, entity, act.get('v'))
    follow_rolling(act.get('cv'))
    wear_gear_on(entity, act.get('g'))
    if act == last:
        return False
    _acts[battle_id] = dict(act)
    try:
        if act.get('pl') != last.get('pl'):
            entity.setVisible(not act.get('pl'))
    except Exception:
        if once('act-visible'):
            log_error('local-battle-act-visible-error')
    if act.get('f') != last.get('f') and act.get('f') is not None:
        set_player_field(entity, 'fallPhase', int(act['f']))
    if act.get('p') != last.get('p') and act.get('p') is not None:
        apply_pose(entity, int(act['p']))
    if act.get('l') != last.get('l') and act.get('l') is not None:
        set_player_field(entity, 'leanState', int(act['l']))
    guns = list(act.get('w') or [])
    for slot, gun in enumerate(guns[:BOMB_SLOT + 1]):
        if last.get('w') and len(last['w']) > slot and last['w'][slot] == gun:
            continue
        put_remote_weapon(entity, slot, int(gun or 0))
    if act.get('pt') is not None:
        try:
            entity.pitch = float(act['pt'])     # where they aim, up or down
        except Exception:
            pass
    for key, callback, args in (('js', 'onJumpStart', ()), ('je', 'onJumpEnd', (JUMP_LANDED,))):
        if last and int(act.get(key) or 0) > int(last.get(key) or 0):
            try:
                getattr(entity, callback)(*args)  # the jump, as the server broadcast it
            except Exception:
                if once('act-' + callback):
                    log_error('local-battle-act-jump-error', callback=callback)
    return True


_jumps = {'start': 0, 'end': 0}
JUMP_LANDED = 0                         # PlayerAnimationTreeManager.onJumpEnd(phase): a normal landing


def on_jump_start(player, *_args, **_kwargs):
    """cell.jumpStart: counted for the other windows (they play the jump on
    this body).  Nothing is called back here - the jumper's own onJumpStart
    sends jumpStart again, and calling it looped the game until it froze."""
    _jumps['start'] += 1
    return None


def on_jump_end(player, *_args, **_kwargs):
    _jumps['end'] += 1
    return None


def hand_weapon(entity, current, guns):
    """The weapon in their hands is the one they hold - checked every
    update, so a body that drifted (or was told something else) is put right.
    A gun slot with no gun in it is never handed over."""
    if current is None:
        return False
    current = int(current)
    if current in GUN_SLOTS + (PISTOL_SLOT, BOMB_SLOT) and guns and len(guns) > current             and not int(guns[current] or 0):
        current = MELEE_SLOT                    # nothing in that slot: never an empty one in hand
    try:
        old = int(getattr(entity, 'dtsCurWeapon', MELEE_SLOT) or 0)
    except Exception:
        old = MELEE_SLOT
    if old == current:
        return False
    set_player_field(entity, 'dtsCurWeapon', current)
    try:
        entity.onOtherChangeDtsWeapon(old, current)
    except Exception:
        if once('hand-weapon'):
            log_error('local-battle-hand-weapon-error')
    return True


WORN_GEAR = ('dtsHelmet', 'dtsVest', 'dtsPackage')


def wear_gear_on(entity, gear):
    """Their helmet, vest and backpack: the fields their body is drawn from
    (set_dtsHelmet / set_dtsVest redress it; a backpack also needs
    onOtherWearDtsPackage, which swaps the bag model)."""
    if not gear:
        return False
    changed = False
    for field, value in zip(WORN_GEAR, list(gear)):
        value = int(value or 0)
        if int(getattr(entity, field, 0) or 0) == value:
            continue
        set_player_field(entity, field, value)
        changed = True
        if field == 'dtsPackage':
            try:
                entity.onOtherWearDtsPackage()
            except Exception:
                if once('gear-package'):
                    log_error('local-battle-gear-package-error')
    return changed


def put_remote_weapon(entity, slot, gun):
    field = 'dtsWeapon%d' % slot
    try:
        record = getattr(entity, field)
        if hasattr(record, 'keys'):
            if weapon_id(record) == gun:
                return False
            record['weaponID'] = gun
        else:
            setattr(entity, field, gun if gun else (UNARMED if slot == MELEE_SLOT else 0))
        # iDtsEquip.onOtherWearDtsWeapon: what another player's body draws a
        # gun with (onWearDtsWeapon is the own player's - it has no weapon bag).
        entity.onOtherWearDtsWeapon(slot)
        return True
    except Exception:
        if once('act-weapon-%d' % slot):
            log_error('local-battle-act-weapon-error', slot=slot)
        return False


LOOK_DICTS = ('gunID2AppearanceIDDict', 'landVehicleID2AppearanceIDDict')


def my_look(player):
    """The look the others make our body with: battle_appearance's lists,
    gun skins, character and clothes."""
    try:
        values = battle_appearance(player)
    except Exception:
        return {}
    return dict((key, value) for key, value in values.items()
                if key not in ('dtsAppearanceSuitReplaceDict', 'dtsWeaponDanceClipReplaceInfo'))


def look_properties(look):
    out = {}
    for key, value in look.items():
        if key in LOOK_DICTS and isinstance(value, dict):
            try:
                value = dict((int(k), int(v)) for k, v in value.items())
            except Exception:
                value = {}
        out[str(key)] = value
    out['dtsAppearanceSuitReplaceDict'] = {}
    out['dtsWeaponDanceClipReplaceInfo'] = {}
    return out


# --------------------------------------------------------------------------
# The battle relay.  What the old server passed on from one player to the
# others: the game's own broadcast calls (a shot, its tracer, where it hit,
# an arrow, a weapon change...) are sent with the next position and played,
# in every other window, on that player's body with the call the server used
# (onFire, onBroadcastShootSegment, onBroadcastShootHitScene, ...); doors,
# glass, grenades and shells likewise, as events of their own.
# --------------------------------------------------------------------------

_relay = {'out': [], 'seen': None}
RELAY_OUTBOX = 40


def plain(value, depth=0):
    """Game values as JSON: vectors as [x, y, z], ids as ints."""
    if hasattr(value, 'x') and hasattr(value, 'y') and hasattr(value, 'z'):
        try:
            return [float(value.x), float(value.y), float(value.z)]
        except Exception:
            return None
    if isinstance(value, (bool, int, long_type, float)) or value is None:
        return value
    if isinstance(value, (str,)) or type(value).__name__ == 'unicode':
        return value
    if depth > 3:
        return None
    if isinstance(value, (list, tuple)):
        return [plain(item, depth + 1) for item in value]
    if isinstance(value, dict):
        return dict((str(key), plain(item, depth + 1)) for key, item in value.items())
    return None


def emit(kind, data):
    if BATTLE.get('phase') != 'fighting':
        return False
    _relay['out'].append({'kind': kind, 'data': data})
    del _relay['out'][:-RELAY_OUTBOX]
    return True


def take_outbox():
    out, _relay['out'] = _relay['out'][:20], _relay['out'][20:]
    return out


def apply_events(snapshot):
    if _relay['seen'] is None:
        _relay['seen'] = int(snapshot.get('event_seq') or 0)     # joined now: not the round's history
        return 0
    played = 0
    for event in snapshot.get('events') or []:
        seq = int(event.get('seq') or 0)
        if seq <= _relay['seen']:
            continue
        _relay['seen'] = seq
        try:
            play_event(event)
            played += 1
        except Exception:
            if once('event-' + str(event.get('kind'))):
                log_error('local-battle-event-error', kind=event.get('kind'))
    return played


def body_of(battle_id):
    """A battle-host id as an entity here: another player's body, or ours."""
    if battle_id is None:
        return None
    if int(battle_id) == int(BATTLE.get('entity_id') or 0):
        return current_player()
    handle = _remote.get(int(battle_id))
    body = _resolve_entity(handle) if handle is not None else None
    return None if isinstance(body, (int, long_type)) else body


def vec(value):
    vector = getattr(sys.modules.get('Math'), 'Vector3', None)
    try:
        return vector(*[float(item) for item in value[:3]]) if vector is not None else tuple(value)
    except Exception:
        return value


def play_event(event):
    kind, data = event.get('kind'), event.get('data') or {}
    if kind == 'rpc':
        return replay_rpc(body_of(event.get('from')), data.get('n'), list(data.get('a') or []))
    if kind == 'door':
        space = zone_space()
        if data.get('open'):
            local_open_element(space, data.get('id'), data.get('state', 1), relayed=True)
        else:
            local_close_element(space, data.get('id'), relayed=True)
        return True
    if kind == 'glass':
        return replay_glass(data.get('id'))
    if kind == 'sing':
        return replay_sing(body_of(event.get('from')), bool(data.get('on')))
    if kind == 'car':
        key = data.get('key')
        if not key or key in _car_keys:
            return False
        x, y, z = _point(data.get('pos') or (0.0, 0.0, 0.0))
        car_id = spawn_vehicle(str(data.get('class') or 'LandCar'), int(data.get('land') or 0),
                               int(data.get('tps') or 0), x, z, y, float(data.get('yaw') or 0.0))
        if car_id is not None:
            share_car(car_id, key)
        return car_id is not None
    if kind in ('car_hit', 'car_die'):
        return replay_car_hit(kind, body_of(event.get('from')), data)
    if kind == 'heritage':
        victim = event.get('from')
        items = [(entry[0], entry[1]) for entry in data.get('items') or [] if isinstance(entry, (list, tuple))]
        name = data.get('name') or _player_names.get(victim) or 'Player'
        return drop_heritage(victim, name, data.get('pos') or (0.0, 0.0, 0.0), items) is not None
    if kind == 'car_fx':
        return replay_car_fx(data)
    if kind == 'airdrop':
        x, y, z = _point(data.get('spot') or (0.0, 0.0, 0.0))
        return drop_supply(_airdrops['token'], int(data.get('index') or 0), (x, y, z, 'relayed'))
    if kind == 'throw':
        return throw_bomb(current_player(), int(data.get('rail') or 0), data.get('info') or {}, relayed=True)
    if kind == 'shell':
        info = dict(data.get('info') or {})
        info['relayed'] = 1
        return fire_range_shot(current_player(), int(data.get('bullet') or 0), int(data.get('rail') or 0),
                               int(data.get('item') or 0), info)
    return False


class Hitter(object):
    """Who hit a car, for the car's damage call: only their id is read."""

    def __init__(self, entity_id=0):
        self.id = entity_id


def replay_car_hit(kind, attacker, data):
    """Another player shot or blew up a car: the same hit on our copy of it
    (its HP, the damage it shows), and its wreck when it is destroyed."""
    car_id = _car_keys.get(data.get('key'))
    car = vehicle_entity(car_id)
    record = _vehicles.get(car_id)
    if car is None or record is None or record.get('dead'):
        return False
    hitter = attacker if attacker is not None else Hitter()
    hit_type = int(data.get('ht') or HIT_SHOOT)
    part = int(data.get('part') or 0)
    src = _point(data['src']) if data.get('src') else _point(getattr(attacker, 'position', None) or car.position)
    weapon = weapon_record(0, 0, hit_type)
    if kind == 'car_die':
        try:
            car.hp = 0
        except Exception:
            pass
        return explode_vehicle(hitter, car, src, weapon, part, hit_type, relayed=True)
    return damage_vehicle(hitter, car_id, int(data.get('dmg') or 0), src, hit_type, part, weapon,
                          relayed=True) is not None


def replay_sing(body, on):
    """PlayerTPAppear.onSingStart / onSingStop on their body: the use of a
    medkit, a bandage, a drink, as the others saw it online."""
    if body is None:
        return False
    try:
        body.gameObject.SendMessage('onSingStart' if on else 'onSingStop')
        return True
    except Exception:
        if once('replay-sing'):
            log_error('local-battle-replay-sing-error')
        return False


def replay_glass(breakable):
    if breakable is None or breakable in _broken:
        return False
    scene = _scene_system()
    breaker = getattr(scene, 'breakElement', None) if scene is not None else None
    if not callable(breaker):
        return False
    breaker(int(breakable))
    _broken.add(int(breakable))
    return True


def replay_throw(profile, info):
    start = _point(info.get('startPos') or (0.0, 0.0, 0.0))
    end = _point(info.get('endPos') or start)
    bomb = profile['bomb']
    impact = int(getattr(bomb, 'EXPLODE_TYPE', 1) or 1) == IMPACT_EXPLODE
    fuse = IMPACT_TIMEOUT if impact else max(MIN_FUSE, float(info.get('lifespan') or
                                                                getattr(bomb, 'EXPLODE_TIME', 3.0) or 3.0))
    key = launch_visual(bomb, start, end, impact)
    _flights[key]['blast'] = (profile, 0)
    _flights[key]['harmless'] = True
    call_later(fuse, detonate_flight, key)
    return True


# cell RPC the game sends -> what the server called on the sender's body in
# every other client (and how the arguments map)
RELAYED_RPCS = ('fire', 'fireEnd', 'broadcastFireMessage', 'broadcastShootHitScene', 'broadcastShootHitEntity',
                'broadcastColdWeaponHitScene', 'broadcastCreateBowBullet', 'chargeFireStart',
                'playAnimation', 'stopAnimation')
# Not changeDtsWeapon: that is a request (pressing 1 on an empty slot asks,
# and nothing changes); relayed, the other window put the empty slot in the
# body's hands - the game draws a default AK-47 for it.  The weapon in hand
# comes with every position instead (my_act 'c') and is applied as it is.


def install_relays(handlers):
    for name in RELAYED_RPCS:
        original = handlers.get(name)
        if getattr(original, '_rl_relay', False):
            continue
        handlers[name] = relay_handler(name, original)
    return True


def relay_handler(name, original):
    def handler(player, *args, **kwargs):
        try:
            emit('rpc', {'n': name, 'a': relay_args(name, args)})
        except Exception:
            if once('relay-' + name):
                log_error('local-battle-relay-error', rpc=name)
        if callable(original):
            return original(player, *args, **kwargs)
        return None
    handler._rl_relay = True
    return handler


def relay_args(name, args):
    args = [plain(arg) for arg in args]
    if name == 'broadcastShootHitEntity' and args:
        hit = int(args[0] or 0)                 # an entity id here: as the battle host knows it
        if hit == getattr(current_player(), 'id', None):
            args[0] = {'bid': BATTLE.get('entity_id')}
        else:
            bid = battle_id_of(_resolve_entity(remote_by_id(hit)) or hit)
            args[0] = {'bid': bid}
    if name == 'changeDtsWeapon':
        args = [int(getattr(current_player(), 'dtsCurWeapon', 0) or 0)] + args
    return args


def remote_by_id(entity_id):
    for _battle_id, entity in remote_bodies():
        if getattr(entity, 'id', None) == entity_id:
            return entity
    return None


def replay_rpc(body, name, args):
    if body is None or not name:
        return False
    if name == 'fire':
        return body.onFire()
    if name == 'fireEnd':
        return body.onFireEnd()
    if name == 'broadcastFireMessage' and len(args) >= 2:
        return body.onBroadcastShootSegment(vec(args[0]), vec(args[1]))
    if name in ('broadcastShootHitScene', 'broadcastColdWeaponHitScene') and len(args) >= 3:
        handler = 'onBroadcastShootHitScene' if name == 'broadcastShootHitScene' else 'onBroadcastColdWeaponHitScene'
        weapon = args[3] if len(args) > 3 else 0
        return getattr(body, handler)(args[0], vec(args[1]), vec(args[2]), weapon)
    if name == 'broadcastShootHitEntity' and len(args) >= 3:
        target = body_of((args[0] or {}).get('bid')) if isinstance(args[0], dict) else None
        if target is None:
            return False
        rest = list(args[3:]) + [0, 0, 0]
        return body.onBroadcastShootHitEntity(body.id, target.id, vec(args[1]), vec(args[2]),
                                              rest[0], rest[1], rest[2])
    if name == 'broadcastCreateBowBullet' and len(args) >= 2:
        rest = list(args[2:]) + [0] * 7
        return body.onBroadcastCreateBowBullet(body.id, vec(args[0]), vec(args[1]), *rest[:7])
    if name == 'chargeFireStart':
        return body.onChargeFireStart()
    if name == 'playAnimation' and args:
        return body.playAnimation(*args[:3])        # drinks, the energy shot ('fire_hormone')...
    if name == 'stopAnimation':
        return body.stopAnimation()
    if name == 'changeDtsWeapon' and len(args) >= 2:
        old, new = int(args[0] or 0), int(args[1] or 0)
        set_player_field(body, 'dtsCurWeapon', new)
        return body.onOtherChangeDtsWeapon(old, new)
    return False


# --------------------------------------------------------------------------
# Player against player.  The battle host keeps every player's HP: a hit on
# another player is sent to it (shown here at once, its HP from the host);
# the hits we took come back in our own state, with the game's damage call
# (where it came from), and at 0 HP we die, killed by them - results screen,
# "killed you".  Their window sees the kill in the feed and counts it.
# --------------------------------------------------------------------------

_kinds = {}
_pvp = {'hits': [], 'died': None, 'hurt_seen': 0, 'killed': False, 'reborn': False, 'taken': []}


def is_player_body(target):
    battle_id = battle_id_of(target)
    return battle_id is not None and _kinds.get(battle_id) == 'player'


def hit_player(player, target, damage, src_pos, hit_part, hit_type, weapon, weapon_name):
    amount = int(round(damage))
    if amount <= 0:
        return None
    try:
        old = int(target.hp)
    except Exception:
        old = FULL_HP
    shown = max(1, old - amount)                # the host decides when they die
    count_stat('damage', min(amount, old))
    count_weapon(weapon, 'damage', min(amount, old))
    if not broadcast(target, 'damage', (player.id, src_pos, weapon, amount, shown, hit_part, hit_type)):
        show_damage_text(target.position, amount, hit_type, hit_part)
    gun = weapon.get('weaponID') if isinstance(weapon, dict) else 0
    # the host says who died (credit_player_kill): the kill goes to the gun that hit last
    _round.setdefault('last_gun', {})[battle_id_of(target)] = int(gun or 0)
    _pvp['hits'].append({'target': battle_id_of(target), 'damage': amount, 'part': int(hit_part or 0),
                         'hit_type': int(hit_type or 1), 'weapon': str(weapon_name or ''), 'gun': int(gun or 0),
                         'src': list(_point(src_pos)) if src_pos is not None else None})
    del _pvp['hits'][:-40]
    return shown


def keep_remote_hp(entity, hp):
    try:
        if int(getattr(entity, 'hp', hp)) != hp:
            entity.hp = hp
    except Exception:
        pass


def take_hits():
    hits, _pvp['hits'] = _pvp['hits'][:20], _pvp['hits'][20:]
    return hits


def take_death():
    died, _pvp['died'] = _pvp['died'], None
    return died


def apply_own_state(state):
    """The hits we took from other players, and our death by them."""
    if not isinstance(state, dict):
        return False
    player = current_player()
    if player is None:
        return False
    for hurt in state.get('hurts') or []:
        seq = int(hurt.get('seq') or 0)
        if seq <= _pvp['hurt_seen']:
            continue
        _pvp['hurt_seen'] = seq
        take_player_hit(player, hurt)
    if state.get('alive') is False and not _pvp['killed'] and int(state.get('killer_id') or 0):
        _pvp['killed'] = True
        killed_by_player(player, state)
    return True


def take_player_hit(player, hurt):
    try:
        old = int(player.hp)
    except Exception:
        return False
    new = max(0, min(old, int(hurt.get('hp', old - int(hurt.get('damage') or 0)))))
    attacker = body_of(hurt.get('from'))
    _pvp['taken'].append(dict(hurt))
    del _pvp['taken'][:-MAX_TAKEN]
    source = _point(hurt.get('src') or (attacker.position if attacker is not None else player.position))
    player.hp = max(1, new) if new <= 0 else new  # death comes with the state (killer, weapon)
    weapon = weapon_record(0, 0, int(hurt.get('hit_type') or HIT_SHOOT))
    broadcast(player, 'damage', (getattr(attacker, 'id', 0), source, weapon, int(hurt.get('damage') or 0),
                                 player.hp, int(hurt.get('part') or 0), int(hurt.get('hit_type') or HIT_SHOOT)))
    changed = getattr(player, 'set_hp', None)
    if callable(changed):
        try:
            changed(old)
        except Exception:
            if once('pvp-set-hp'):
                log_error('local-battle-pvp-hp-error')
    return True


def killed_by_player(player, state):
    killer = str(state.get('killer') or 'Player')
    weapon = str(state.get('weapon') or '')
    attacker = body_of(state.get('killer_id'))
    try:
        player.hp = 0
    except Exception:
        pass
    show_kill_feed(killer, weapon, avatar_name(player), getattr(attacker, 'id', 0), player.id)
    log('local-battle-killed-by-player', killer=killer, weapon=weapon, island=on_island_stage())
    if on_island_stage():
        return island_death(player, killer)
    show_killer_overview(player, state, attacker)
    _pvp['killer_body'] = getattr(attacker, 'id', 0)
    call_later(OBSERVE_KILLER_DELAY, observe_body, attacker)
    return player_died(player, DEATH_PLAYER, _point(attacker.position) if attacker is not None else None)


OBSERVE_KILLER_DELAY = 1.5


def camera_controller():
    try:
        from libclaudia import Camera
        return Camera.main.gameObject.GetComponent('PlayerCameraController')
    except Exception:
        return None


def observe_body(body):
    """The camera on another player (who killed you): it follows them, as
    the old server's observe did, instead of staying on your body."""
    controller = camera_controller()
    if controller is None or body is None:
        return False
    try:
        controller.setToObserverMode(body.gameObject)
        log('local-battle-observe', target=getattr(body, 'id', None))
        return True
    except Exception:
        if once('observe-body'):
            log_error('local-battle-observe-error')
        return False


def on_observe_killer(player, killer_id=0, *_args, **_kwargs):
    """The results' Spectate button (cell.requestObserveKiller)."""
    try:
        killer_id = int(killer_id or _pvp.get('killer_body') or 0)
    except Exception:
        killer_id = 0
    body = remote_by_id(killer_id)
    if body is not None:
        call_later(0.0, observe_body, body)
    return None


ISLAND_RESPAWN_SECONDS = 3.0
MAX_TAKEN = 60


def on_island_stage():
    return _flight.get('stage') == 'island'


def island_death(player, killer):
    """The Prepare Island: nobody is out before the plane leaves - a death
    there puts you back on the island in a moment, at full health."""
    tip_text('%s got you - back in %d s' % (killer, int(ISLAND_RESPAWN_SECONDS)))
    call_later(ISLAND_RESPAWN_SECONDS, island_respawn, player)
    return True


def island_respawn(player):
    if not on_island_stage() or BATTLE.get('phase') != 'fighting':
        return False
    point = island_reborn_point(BATTLE.get('map'))
    try:
        old = int(player.hp)
        player.hp = int(getattr(player, 'maxHp', FULL_HP) or FULL_HP)
        changed = getattr(player, 'set_hp', None)
        if callable(changed):
            changed(old)
    except Exception:
        if once('island-respawn-hp'):
            log_error('local-battle-island-respawn-error')
    if point is not None:
        land_player(player, (point[0], point[1] + STAND_HEIGHT, point[2]))
    _pvp['killed'] = False
    _pvp['reborn'] = True
    _pvp['taken'][:] = []
    log('local-battle-island-respawn', position=[round(v) for v in point] if point else None)
    return True


def take_reborn():
    reborn, _pvp['reborn'] = _pvp.get('reborn', False), False
    return reborn


def _shared_const(group, name, fallback):
    for module_name in ('shared.shared_const', 'shared_const', 'shared.const', 'const'):
        try:
            module = __import__(module_name, fromlist=[group])
            value = getattr(getattr(module, group), name)
            return value
        except Exception:
            continue
    return fallback


def as_list(value):
    try:
        return [int(item) for item in list(value or [])]
    except Exception:
        return []


def show_killer_overview(player, state, killer_body):
    """iBattleGround.showKillerOverview, as the server called it at your
    death: the killer as a model with the gun that did it, their gear, and
    who dealt how much (UIDeathKillerDisplay), before the results."""
    killer_id = int(state.get('killer_id') or 0)
    hurts = [hurt for hurt in _pvp['taken'] if int(hurt.get('from') or 0)]
    by_killer = [hurt for hurt in hurts if int(hurt.get('from') or 0) == killer_id]
    last = by_killer[-1] if by_killer else {}
    player_type = _shared_const('DamageSourceType', 'Player', 1)
    totals = {}
    for hurt in hurts:
        attacker = int(hurt.get('from') or 0)
        body = body_of(attacker)
        entry = totals.setdefault(attacker, {'type': player_type, 'entityID': getattr(body, 'id', 0),
                                             'name': str(hurt.get('name') or 'Player'), 'damage': 0})
        entry['damage'] += int(hurt.get('damage') or 0)
    killer_source = totals.get(killer_id) or {'type': player_type, 'entityID': getattr(killer_body, 'id', 0),
                                               'name': str(state.get('killer') or 'Player'), 'damage': 0}
    body = killer_body
    info = {
        'playerInfo': {
            'identityType': _shared_const('PlayerIdentity', 'Normal', 0),
            'characterType': int(getattr(body, 'characterType', DEFAULT_CHARACTER_TYPE) or DEFAULT_CHARACTER_TYPE),
            'equips': [value for value in (int(getattr(body, field, 0) or 0) for field in WORN_GEAR) if value],
            'dtsBodyAppearanceList': as_list(getattr(body, 'dtsBodyAppearanceList', [])),
            'dtsWearableAppearanceList': as_list(getattr(body, 'dtsWearableAppearanceList', [])),
            'dtsBattlegroundPropAppearanceList': as_list(getattr(body, 'dtsBattlegroundPropAppearanceList', [])),
            'dtsWeaponAppearanceList': as_list(getattr(body, 'dtsWeaponAppearanceList', [])),
            'weaponInfo': {'weaponID': int(last.get('gun') or 0), 'WeaponName': str(state.get('weapon') or '')},
            'hitInfo': ElementRecord(hitType=int(last.get('hit_type') or HIT_SHOOT)),
            'dtsNameplateAppearance': 0,
        },
        'damageSource': killer_source,
    }
    try:
        player.showKillerOverview(info, list(totals.values()) or [killer_source])
        return True
    except Exception:
        if once('killer-overview'):
            log_error('local-battle-killer-overview-error')
        return False


def credit_player_kill(target, item):
    player = current_player()
    if player is None:
        return False
    bump(player, 'battleKillNum', 1)
    count_stat('kills')
    count_weapon((_round.get('last_gun') or {}).get(battle_id_of(target)), 'kills')
    victim = str(item.get('name') or avatar_name(target))
    weapon = str(item.get('weapon') or '')
    texts = sys.modules.get('errtxt')
    mine = getattr(texts, MY_KILL_TEXT, None) or MY_KILL_TEXT_FALLBACK
    try:
        player.dtsKillTip(mine % (weapon, victim))
    except Exception:
        if once('pvp-kill-tip'):
            log_error('local-battle-pvp-kill-tip-error')
    log('local-battle-player-kill', victim=victim, weapon=weapon)
    return True


# --------------------------------------------------------------------------
# Cars.  Every window lays the map's cars out the same way; each has a key
# (its spawn spot).  Who sits in which seat comes with every position, and
# the driver's window sends where the car is: the others seat that player's
# body in their copy of the car (as the car's own seat list does it,
# usedHangSockets + onGetOn) and drive it there, gliding like the bodies.
# --------------------------------------------------------------------------

_car_keys = {}                                  # key -> car entity id here
_seated = {}                                    # battle id -> (key, socket)
_car_motion = {}                                # key -> {'samples': [...]}


def share_car(car_id, key):
    _car_keys[key] = car_id
    _vehicles.setdefault(car_id, {})['key'] = key
    return True


def my_vehicle(player):
    if not getattr(player, 'inLandVehicle', False):
        return None
    car = vehicle_entity(getattr(player, 'vehicleEntID', 0))
    key = _vehicles.get(getattr(car, 'id', None), {}).get('key') if car is not None else None
    if key is None:
        return None                             # a car only this window has (/spawn car)
    seat = {'k': key, 's': str(getattr(player, 'hangSockName', '') or '')}
    if getattr(player, 'isLandDriver', False):
        seat['d'] = 1
        point, yaw = car_pose(car)
        seat['p'] = [round(value, 2) for value in point]
        seat['y'] = round(yaw, 4)
        seat['t'] = [round(value, 1) for value in car_tilt(car)]
    return seat


def signed_degrees(value):
    return (float(value) + 180.0) % 360.0 - 180.0


def car_tilt(car):
    """(pitch, roll) of the car in degrees, -180..180."""
    try:
        euler = car.gameObject.transform.eulerAngles
        return signed_degrees(euler.x), signed_degrees(euler.z)
    except Exception:
        return 0.0, 0.0


def car_pose(car):
    """Where the car really is while it is driven here: its model (the
    physics move the transform; the entity's position stays where the car
    was made, so the others saw it stand still), heading from its nose."""
    try:
        transform = car.gameObject.transform
        point = _point(transform.position)
        forward = _point(transform.forward)
        return point, math.atan2(forward[0], forward[2])
    except Exception:
        return _point(car.position), float(getattr(car, 'yaw', 0.0) or 0.0)


def sync_vehicle(battle_id, body, seat):
    was = _seated.get(battle_id)
    if not seat:
        if was is not None:
            unseat_body(battle_id, body, was)
        else:
            leave_seat_look(body)               # out of every car, yet still drawn sitting
        return False
    key, socket = seat.get('k'), seat.get('s')
    car = vehicle_entity(_car_keys.get(key))
    if car is None:
        return False                            # not streamed in here yet
    if was != (key, socket):
        if was is not None and was[0] != key:
            unseat_body(battle_id, body, was)
        seat_body(battle_id, body, car, key, socket)
    if seat.get('d') and seat.get('p'):
        glide = _car_motion.setdefault(key, {'samples': []})
        glide['driven'] = True
        glide['tilt'] = seat.get('t')
        glide['samples'].append((time.time(), _point(seat['p']), float(seat.get('y') or 0.0)))
        del glide['samples'][:-MOTION_KEEP]
        run_motion()
    return True


def seat_body(battle_id, body, car, key, socket):
    """Another player in a seat of our copy of the car."""
    try:
        prepare_vehicle(car)
        driver = socket == VEHICLE_DRIVER_SOCKET
        body.inLandVehicle = True
        body.isLandDriver = driver
        body.isDriver = int(driver)
        body.vehicleEntID = car.id
        body.hangSockName = socket
        body.sockNameOnCar = socket
        seats = [item for item in list(car.usedHangSockets or []) if item.get('id') != body.id]
        set_seats(car, seats + [{'sockname': socket, 'id': body.id}])
        car.onGetOn(body.id)
        refresh_seats(car)
    except Exception:
        if once('seat-body'):
            log_error('local-battle-seat-body-error', car=key)
        return False
    _seated[battle_id] = (key, socket)
    log('local-battle-remote-get-on', player=battle_id, car=key, seat=socket)
    return True


def detach_body(car, body, socket):
    """The car's seat let go of the body (pullAvatarSocketInfo bound it with
    msgEnterHangOnCar + bindPlayer; nothing undid it for another player, so
    after getting out their body stayed drawn in the seat)."""
    try:
        body.msgLeaveHangOnCar(getattr(car, 'driveCarType', 0), car.id, socket,
                               getattr(car, 'tpsVehicleID', 0))
    except Exception:
        if once('leave-hang'):
            log_error('local-battle-leave-hang-error')
    try:
        message_args = getattr(sys.modules.get('iVehicleEntity'), 'MessageArgs', None)
        if message_args is not None:
            car.SendMessage('unbindPlayer', message_args(bindGameObj=body.gameObject))
    except Exception:
        if once('unbind-player'):
            log_error('local-battle-unbind-error')
    try:
        # The seat's animation ends with a pose change from DRIVE (the body
        # sat on in the air where the car had been, its pose already 0).
        body.onUpdatePose(POSE_DRIVE, int(getattr(body, 'pose', 0) or 0))
    except Exception:
        if once('leave-pose'):
            log_error('local-battle-leave-pose-error')
    leave_seat_look(body, car, socket)
    return True


def leave_seat_look(body, car=None, socket=''):
    """The body's look (PlayerTPAppear) still sitting: isInVehicle stayed
    set, and its animations stayed on the seat's (drive / hang).  The
    look's own leaving does what the old server's get-off did for it: the
    weapon back, onDrivingEnd, the normal animations."""
    try:
        appear = body.gameObject.GetComponent('PlayerTPAppear')
    except Exception:
        return False
    if appear is None or not getattr(appear, 'isInVehicle', False):
        return False
    try:
        if getattr(appear, 'isHangOnCar', False):
            appear.msgLeaveHangOnCar(getattr(car, 'driveCarType', 0), getattr(car, 'id', 0), socket or '',
                                     getattr(car, 'tpsVehicleID', 0))
        else:
            manager = getattr(appear, 'animMgr', None)
            appear.onExitVehicle(bool(getattr(manager, '_isDriver', True)))
    except Exception:
        if once('leave-seat-look'):
            log_error('local-battle-leave-seat-look-error')
        return False
    return True


def unseat_body(battle_id, body, was):
    _seated.pop(battle_id, None)
    car = vehicle_entity(_car_keys.get(was[0]))
    try:
        if car is not None:
            detach_body(car, body, was[1])
            set_seats(car, [item for item in list(car.usedHangSockets or []) if item.get('id') != body.id])
            car.onGetOff(body.id)
            refresh_seats(car)
        clear_seat(body)
        # A car that hides who sits in it (HIDE_HANG_PLAYER) does not show
        # another player's body again when they get out: shown here.
        body.setVisible(True)
    except Exception:
        if once('unseat-body'):
            log_error('local-battle-unseat-body-error', car=was[0])
        return False
    if was[1] == VEHICLE_DRIVER_SOCKET or not any(seated[0] == was[0] for seated in _seated.values()):
        _car_motion.pop(was[0], None)           # nobody drives it now: it stays where it was left
        if car is not None and was[0] in _engines:
            engine_running(car, was[0], False)
    log('local-battle-remote-get-off', player=battle_id, car=was[0])
    return True


def remote_died(battle_id, handle, item):
    """Someone in another game window killed it (the battle host says
    alive: false): it dies here too, with the kill in the feed and its death
    box (the same box in every window)."""
    target = _resolve_entity(handle)
    if target is None or isinstance(target, (int, long_type)):
        return False
    _dead.add(target.id)
    try:
        target.hp = 0
    except Exception:
        pass
    weapon = weapon_record(0, 0, HIT_SHOOT)
    position = _point(target.position)
    if not broadcast(target, 'die', (0, position, weapon, CHEST_PART, HIT_SHOOT)):
        try:
            target.onDie(position, 0, weapon, CHEST_PART, HIT_SHOOT)
        except Exception:
            if once('remote-die'):
                log_error('local-battle-remote-die-error', target=battle_id)
    show_kill_feed(str(item.get('killer') or 'Player'), str(item.get('weapon') or ''),
                   str(item.get('name') or avatar_name(target)), 0, target.id)
    if item.get('kind') == 'player' and int(item.get('killer_id') or 0) == int(BATTLE.get('entity_id') or -1) \
            and not on_island_stage():
        credit_player_kill(target, item)
    call_later(BODY_LINGER, bury_body, battle_id)
    log('local-battle-remote-kill', target=battle_id, killer=item.get('killer'), weapon=item.get('weapon'))
    return True


def show_kill_feed(killer, weapon_name, victim, killer_id, victim_id):
    texts = sys.modules.get('errtxt')
    feed = getattr(texts, KILL_TEXT, None) or KILL_TEXT_FALLBACK
    try:
        import Globals
        Globals.spaceEntity.showKillInfo(feed, ([killer, weapon_name, victim],), '',
                                         {'killerID': killer_id, 'killedID': victim_id, 'isWounded': False})
        return True
    except Exception:
        if once('kill-feed-remote'):
            log_error('local-battle-kill-feed-error')
        return False


_player_names = {}                     # battle id -> another player's name


LEFT_TEXT_FALLBACK = '%s has left the game'


def announce_left(battle_id):
    """Another player quit the round (gone from the battle host's world
    while still alive): every window says so in the kill feed.  The LEFT
    count drops with it; the last one standing wins - not on the island,
    where the round has not begun."""
    if _kinds.get(battle_id) != 'player':
        return False
    handle = _remote.get(battle_id)
    body = _resolve_entity(handle) if handle is not None else None
    if battle_id in _buried or getattr(body, 'id', None) in _dead:
        return False                            # dead already: no one left
    name = _player_names.get(battle_id) or avatar_name(body) if body is not None else _player_names.get(battle_id)
    name = name or 'A player'
    text = LEFT_TEXT_FALLBACK
    shown = False
    try:
        import Globals
        Globals.spaceEntity.showKillInfo(text, ([name],), '', {'killerID': 0, 'killedID': 0, 'isWounded': False})
        shown = True
    except Exception:
        if once('left-feed'):
            log_error('local-battle-left-feed-error')
    if not shown:
        tip_text(text % name)
    _kinds.pop(battle_id, None)
    log('local-battle-player-left', player=battle_id, name=name, stage=_flight.get('stage'))
    return True


def sync_alive_count(snapshot):
    """LEFT: everyone the battle host still has alive, and you."""
    if not isinstance(snapshot.get('entities'), list):
        return False
    entities = snapshot['entities']             # empty: everyone else has left
    alive = sum(1 for item in entities if item.get('alive', True) is not False)
    me = current_player()
    if me is not None and int(getattr(me, 'hp', 1) or 0) > 0:
        alive += 1
    try:
        import Globals
        space = Globals.spaceEntity
    except Exception:
        return False
    _round['field'] = max(int(_round.get('field') or 0), alive)
    if space is None or int(getattr(space, 'aliveNum', 0) or 0) == alive:
        return False
    set_alive_count(alive)
    if alive <= 1 and me is not None and int(getattr(me, 'hp', 0) or 0) > 0 and not _round.get('shown') \
            and not _round.get('over') and _flight.get('stage') != 'island':
        call_later(RESULT_DELAY, show_result, me, 1)        # everyone else is dead: we won
    return True


# --------------------------------------------------------------------------
# Shared loot.  Every game window lays the round's loot out the same way
# (seeded by the round's uuid); the battle host keeps what was taken of each
# item (by key) and what was put down, and every snapshot brings both back:
# an item taken in one window goes - or shrinks - in the others, and a gun
# dropped in one lies on the ground in the others.
# --------------------------------------------------------------------------

_shared = {'taken': {}, 'drops': set(), 'dropped': 0}
_boxes = {}                                    # box entity id -> {'key', 'full': {uuid: amount}}


def report_take(key, amount):
    if not key or int(amount or 0) <= 0:
        return False
    _shared['taken'][key] = int(_shared['taken'].get(key, 0)) + int(amount)
    return send(LOOT_PREFIX + json.dumps({'take': key, 'amount': int(amount)}))


def share_box(entity_id, key, items):
    _boxes[entity_id] = {'key': key, 'full': dict((uuid, int(entry[1])) for uuid, entry in items.items())}
    return True


def share_drop(entity_id, prop, amount, position):
    _shared['dropped'] += 1
    key = 'd%s-%d' % (BATTLE.get('entity_id') or 0, _shared['dropped'])
    _shared['drops'].add(key)
    if entity_id in _loot:
        _loot[entity_id].update(key=key, full=int(amount))
    return send(LOOT_PREFIX + json.dumps({'drop': key, 'prop': int(prop), 'amount': int(amount),
                                          'pos': [round(value, 2) for value in position]}))


def apply_shared_loot(snapshot):
    """What the others took and dropped.  Only what changed is worked on: the
    whole round's table came 20 times a second and every item lying in the
    world was walked for it (a battle host from before sends the whole table:
    the unchanged part is skipped here)."""
    if snapshot.get('loot_seq') is not None:
        _shared['loot_seq'] = int(snapshot['loot_seq'])
    if snapshot.get('drop_seq') is not None:
        _shared['drop_seq'] = int(snapshot['drop_seq'])
    taken = snapshot.get('loot')
    if isinstance(taken, dict):
        changed = {}
        for key, amount in taken.items():
            if int(amount) > int(_shared['taken'].get(key, 0)):
                _shared['taken'][key] = int(amount)
                changed[key] = int(amount)
        taken = changed
    if taken:
        for entity_id, record in list(_loot.items()):
            key = record.get('key')
            if not key or key not in taken:
                continue
            left = int(record.get('full', record['amount'])) - int(taken[key])
            if left >= record['amount']:
                continue                        # not news (or our own pickup, already applied)
            if left <= 0:
                remove_loot(entity_id)
            else:
                record['amount'] = left
                resync_amount(entity_id, left)
        for box_id, box in list(_boxes.items()):
            shrink_box(box_id, box, taken)
    for drop in snapshot.get('drops') or []:
        key = drop.get('key')
        if not key or key in _shared['drops']:
            continue
        _shared['drops'].add(key)
        left = int(drop.get('amount') or 1) - int(_shared['taken'].get(key, 0))
        if left <= 0:
            continue
        x, y, z = _point(drop.get('pos') or (0.0, 0.0, 0.0))
        entity_id = spawn_loot(int(drop.get('prop') or 0), left, x, z, y)
        if entity_id is not None:
            _loot[entity_id].update(key=key, full=int(drop.get('amount') or 1))
    return True


def resync_amount(entity_id, amount):
    entity = vehicle_entity(entity_id)
    try:
        entity.syncAmount(amount)
        return True
    except Exception:
        return False


def shrink_box(box_id, box, taken):
    box_entity = vehicle_entity(box_id)
    items = dict(_heritages.get(box_id) or {})
    if box_entity is None or not items:
        return False
    changed = False
    for uuid, full in box['full'].items():
        key = '%s:%s' % (box['key'], uuid)
        if key not in taken or uuid not in items:
            continue
        left = int(full) - int(taken[key])
        if left >= int(items[uuid][1]):
            continue
        changed = True
        if left <= 0:
            items.pop(uuid, None)
        else:
            items[uuid] = [items[uuid][0], left] + list(items[uuid][2:3])
    if not changed:
        return False
    _heritages[box_id] = items
    try:
        box_entity.resetItems(items)
    except Exception:
        box_entity.items = items
    if not items:
        empty_box(box_entity)
    return True


def bury_body(battle_id):
    _buried.add(battle_id)
    _destroy(battle_id)
    return True


def avatar_name(entity):
    name = getattr(entity, 'nickname', None)
    if not name or type(name).__name__ == 'LocalUnknown':
        return 'Player'
    return str(name)


def announce_kill(player, target, weapon_name, headshot):
    texts = sys.modules.get('errtxt')
    victim = avatar_name(target)
    killer = avatar_name(player)
    feed = getattr(texts, KILL_TEXT_HEAD if headshot else KILL_TEXT, None) or KILL_TEXT_FALLBACK
    mine = getattr(texts, MY_KILL_TEXT, None) or MY_KILL_TEXT_FALLBACK
    details = {'killerID': player.id, 'killedID': target.id, 'isWounded': False}
    try:
        import Globals
        space = Globals.spaceEntity
    except Exception:
        space = None
    for step, call in (('feed', lambda: space.showKillInfo(feed, ([killer, weapon_name, victim],), '', details)),
                       ('effect', lambda: space.showKilledUIEffect(details)),
                       ('tip', lambda: player.dtsKillTip(mine % (weapon_name, victim)))):
        try:
            call()
        except Exception:
            if once('kill-' + step):
                log_error('local-battle-kill-notice-error', step=step)
    bump(player, 'battleKillNum', 1)
    if space is not None:
        bump(space, 'aliveNum', -1, floor=1)
        if int(getattr(space, 'aliveNum', 2) or 2) <= 1 and int(getattr(player, 'hp', 0) or 0) > 0:
            call_later(RESULT_DELAY, show_result, player, 1)


def bump(entity, field, step, floor=0):
    try:
        old = int(getattr(entity, field, 0) or 0)
        setattr(entity, field, max(floor, old + step))
    except Exception:
        return False
    changed = getattr(entity, 'set_' + field, None)
    if callable(changed):
        try:
            changed(old)
        except Exception:
            if once('bump-' + field):
                log_error('local-battle-bump-error', field=field)
    return True


BOMB_PROFILES = {}


def bomb_profile(rail_id):
    if rail_id in BOMB_PROFILES:
        return BOMB_PROFILES[rail_id]
    module = _properties_module()
    try:
        _rail, bullet = rail_bullet(rail_id)
        bomb = module.getDtsBombData(int(bullet.BOMB_ID))
        explode = module.getDtsExplodeData(int(bomb.EXPLODE_ID))
    except Exception:
        return None
    profile = {'bomb': bomb, 'explode': explode, 'id': int(bomb.EXPLODE_ID), 'rail': int(rail_id)}
    BOMB_PROFILES[rail_id] = profile
    return profile


# --------------------------------------------------------------------------
# Range guns (grenade launcher, RPG): BulletRangeShot.doFireShot sends
# cell.onDtsRangeGunFire(bulletID, weaponID, railID, itemID, aimed,
# {firePos, fireDir}) and the server flew the shell.  Here it flies from the
# bullet's own data (BULLET_INIT_SPEED, ACC along the way, VER_ACC up/down,
# MAX_SPEED, LIFETIME, MAX_RANGE, MODEL_RES) every frame and, on the ground,
# a wall or a body, goes off as its DAMAGE_CHECK_TYPE's bomb (explosion data,
# effects, sound and damage, as a thrown grenade's).
# --------------------------------------------------------------------------

RANGE_HIT_RADIUS = 8.0                  # this close to a body's middle counts as a hit
RANGE_BODY_LOW = 0.0
RANGE_BODY_HIGH = 20.0
RANGE_MUZZLE_CLEAR = 15.0               # the shell starts this far out of the barrel
RANGE_PROFILES = {}


class RangeBomb(object):
    """What detonate reads of a bomb, for a shell (no smoke, no fuse)."""
    EXPLODE_TIME = 0.0


def range_profile(bullet_id, rail_id):
    key = (int(bullet_id or 0), int(rail_id or 0))
    if key in RANGE_PROFILES:
        return RANGE_PROFILES[key]
    module = _properties_module()
    profile = None
    bullet = None
    try:
        bullet = module.getGunBulletData(int(bullet_id))
    except Exception:
        bullet = None
    if bullet is None:
        _rail, bullet = rail_bullet(rail_id)
    try:
        # RangeBulletSummonDtsBomb.BOMB_ID names the explosion itself (10:
        # the launcher's blast; bomb 10 is the unrelated Red Packet, with no
        # explosion - the shells went off as nothing).
        explode_id = int(bullet.DAMAGE_CHECK_TYPE.BOMB_ID)
        explode = module.getDtsExplodeData(explode_id)
        bomb = RangeBomb()
        model = getattr(bullet, 'MODEL_RES', None)
        profile = {
            'blast': {'bomb': bomb, 'explode': explode, 'id': explode_id, 'rail': int(rail_id)},
            'speed': float(getattr(bullet, 'BULLET_INIT_SPEED', 0.0) or 0.0),
            'acc': float(getattr(bullet, 'ACC', 0.0) or 0.0),
            'drop': float(getattr(bullet, 'VER_ACC', 0.0) or 0.0),
            'max_speed': float(getattr(bullet, 'MAX_SPEED', 0.0) or 0.0),
            'life': float(getattr(bullet, 'LIFETIME', 5.0) or 5.0),
            'range': float(getattr(bullet, 'MAX_RANGE', 4000.0) or 4000.0),
            'model': str(getattr(model, 'MODEL_PATH', '') or ''),
            'fly': str(getattr(model, 'FLY_SOUND', '') or ''),
        }
    except Exception:
        if once('range-profile-%s-%s' % key):
            log_error('local-battle-range-profile-error', bullet=bullet_id, rail=rail_id)
    RANGE_PROFILES[key] = profile
    return profile


def on_range_gun_fire(player, bullet_id=0, weapon_id=0, rail_id=0, item=0, aimed=False, info=None,
                      *_args, **_kwargs):
    try:
        bullet_id, rail_id, item = int(bullet_id or 0), int(rail_id or weapon_id or 0), int(item or 0)
    except Exception:
        return None
    fire_range_shot(player, bullet_id, rail_id, item, info if isinstance(info, dict) else {})
    return None


def fire_range_shot(player, bullet_id, rail_id, item, info):
    profile = range_profile(bullet_id, rail_id)
    if profile is None:
        return None
    muzzle = _point(info.get('firePos') or player.position)
    way = unit(_point(info.get('fireDir') or (0.0, 0.0, 1.0)))
    # The shell goes where the crosshair is.  BulletRangeShot's own way was
    # wrong too often: aimed at what RaycastWithEnemy hit - (0, 0, 0), the
    # middle of the map, when it hit nothing (the ground close by) - or
    # along the gun model, which a jump tilts up into the sky.
    if not info.get('relayed'):
        way = crosshair_way(muzzle, profile['range']) or way
    start = tuple(spot + axis * RANGE_MUZZLE_CLEAR for spot, axis in zip(muzzle, way))
    if not info.get('relayed'):
        emit('shell', {'bullet': int(bullet_id), 'rail': int(rail_id), 'item': int(item),
                       'info': {'firePos': list(muzzle), 'fireDir': list(way), 'relayed': 1}})
    _flight_ids[0] += 1
    key = _flight_ids[0]
    record = {'pos': start, 'way': way, 'speed': profile['speed'], 'climb': 0.0, 'clock': time.time(),
              'age': 0.0, 'travelled': 0.0, 'landed': False, 'go': None, 'range': profile, 'item': item,
              'trail_fx': None, 'blink_fx': None, 'sound': None, 'relayed': bool(info.get('relayed'))}
    fly = profile['fly']
    if fly.endswith('.sfx'):
        record['trail_fx'] = play_effect(fly, start, True)
    elif fly:
        record['sound'] = play_sound(fly, start)
    _flights[key] = record
    close = surface_hit(muzzle, start)
    if close is not None:
        # Point-blank into the ground or a wall: it goes off there.
        record['landed'] = True
        record['pos'] = close[0]
        detonate(profile['blast'], close[0], item, key, harmless=bool(info.get('relayed')))
        log('local-battle-range-shot', item=item, rail=rail_id, at=[round(value, 1) for value in muzzle],
            point_blank=True)
        return key
    load_flight_model(key, profile['model'])
    try:
        player.behaviour.StartCoroutine(range_frames(key))
    except Exception:
        if once('range-frames'):
            log_error('local-battle-range-frames-error')
        call_later(FLIGHT_MAX_STEP, range_tick, key)
    log('local-battle-range-shot', item=item, rail=rail_id, at=[round(value, 1) for value in start])
    return key


AIM_ORIGIN_DOT = 0.9995


def unit(vector):
    size = math.sqrt(sum(value * value for value in vector)) or 1.0
    return tuple(value / size for value in vector)


def aimed_at_origin(start, way):
    towards = unit(tuple(-value for value in start))
    return sum(a * b for a, b in zip(way, towards)) >= AIM_ORIGIN_DOT


def camera_transform():
    try:
        from libclaudia import Camera
        return Camera.main.transform
    except Exception:
        try:
            return sys.modules['libclaudia.Classes.Camera'].Camera.main.transform
        except Exception:
            return None


def crosshair_way(start, reach):
    """From the barrel to what the crosshair is on (the camera's ray: the
    ground, a wall), else straight along it."""
    camera = camera_transform()
    if camera is None:
        return None
    try:
        eye = _point(camera.position)
        forward = unit(_point(camera.forward))
    except Exception:
        return None
    far = tuple(spot + axis * reach for spot, axis in zip(eye, forward))
    hit = surface_hit(eye, far)
    aim = hit[0] if hit is not None else far
    way = unit(tuple(b - a for a, b in zip(start, aim)))
    if sum(a * b for a, b in zip(way, forward)) <= 0.0:
        return forward                          # the crosshair's point is behind the barrel
    return way


def range_frames(key):
    while key in _flights and not _flights[key].get('landed'):
        yield None
        step_range_shot(key, time.time())


def range_tick(key):
    if key in _flights and not _flights[key].get('landed'):
        step_range_shot(key, time.time())
        call_later(FLIGHT_MAX_STEP, range_tick, key)


def range_body_hit(point):
    for _battle_id, entity in remote_bodies():
        if getattr(entity, 'id', None) in _dead:
            continue
        body = _point(entity.position)
        near = math.hypot(point[0] - body[0], point[2] - body[2]) <= RANGE_HIT_RADIUS
        if near and body[1] + RANGE_BODY_LOW <= point[1] <= body[1] + RANGE_BODY_HIGH:
            return entity
    return None


def step_range_shot(key, now):
    record = _flights.get(key)
    if record is None or record.get('landed'):
        return False
    profile = record['range']
    step = min(FLIGHT_MAX_STEP, max(0.0, now - record['clock']))
    record['clock'] = now
    if step <= 0.0:
        return False
    speed = record['speed'] + profile['acc'] * step
    if profile['max_speed'] > 0.0:
        speed = min(speed, profile['max_speed'])
    record['speed'] = speed
    record['climb'] += profile['drop'] * step
    way = record['way']
    x, y, z = record['pos']
    target = (x + way[0] * speed * step, y + (way[1] * speed + record['climb']) * step, z + way[2] * speed * step)
    record['age'] += step
    record['travelled'] += math.sqrt(sum((b - a) ** 2 for a, b in zip(record['pos'], target)))
    contact = surface_hit(record['pos'], target)
    if contact is not None and break_glass(contact[0], contact[1], 'shell') is not None:
        contact = None                          # a window: it shatters and the shell flies on
    point = contact[0] if contact is not None else None
    if point is None and range_body_hit(target) is not None:
        point = target
    if point is None and (record['age'] >= profile['life'] or record['travelled'] >= profile['range']):
        point = target
    if point is not None:
        record['landed'] = True
        record['pos'] = point
        stop_effect(record.get('sound'))
        detonate(profile['blast'], point, record['item'], key, harmless=record.get('relayed', False))
        return True
    record['pos'] = target
    if record.get('go') is not None:
        move_model(record['go'], target)
        face_model(record['go'], (way[0] * speed, way[1] * speed + record['climb'], way[2] * speed))
    if record.get('trail_fx') is not None:
        move_effect(record['trail_fx'], target)
    return False


def face_model(body, heading):
    """Nose first: the shell model turned along where it flies (it was
    left as loaded, side-on to its flight)."""
    physics_module = sys.modules.get('libclaudia.Classes.Physics')
    way = unit(heading)
    try:
        body.transform.forward = physics_module.Vector3(way[0], way[1], way[2])
        return True
    except Exception:
        if once('face-model'):
            log_error('local-battle-face-model-error')
        return False


def on_bomb_throw(player, mode=0, weapon_id=0, rail_id=0, info=None, *_args, **_kwargs):
    try:
        rail_id = int(rail_id or weapon_id)
    except Exception:
        return None
    throw_bomb(player, rail_id, info if isinstance(info, dict) else {})
    return None


IMPACT_EXPLODE = 2
SMOKE_EXPLODE = 3
MIN_FUSE = 0.3
IMPACT_TIMEOUT = 6.0
FLIGHT_GRAVITY = 100.0
FLIGHT_MIN_TIME = 0.2
FLIGHT_MAX_STEP = 0.05
FLIGHT_BOUNCE = 0.45
FLIGHT_FRICTION = 0.7
FLIGHT_REST_SPEED = 12.0
FLIGHT_SKIN = 1.0
GROUND_PROBE = 50.0
EFFECT_ID_BASE = 880000
ONE_SHOT_LIFE = 8.0
LOUD_BOUNCE = 40.0
_flights = {}
_flight_ids = [0]
_effect_ids = [EFFECT_ID_BASE]


def throw_bomb(player, rail_id, info, relayed=False):
    profile = bomb_profile(rail_id)
    if profile is None:
        return False
    if relayed:
        return replay_throw(profile, info)
    emit('throw', {'rail': int(rail_id), 'info': plain(info)})
    item = int(getattr(player, 'dtsWeapon%d' % BOMB_SLOT, 0) or 0)
    use_up_bomb(player, item)
    start = _point(info.get('startPos') or player.position)
    end = _point(info.get('endPos') or start)
    bomb = profile['bomb']
    impact = int(getattr(bomb, 'EXPLODE_TYPE', 1) or 1) == IMPACT_EXPLODE
    if impact:
        fuse = IMPACT_TIMEOUT
    else:
        fuse = max(MIN_FUSE, float(info.get('lifespan') or getattr(bomb, 'EXPLODE_TIME', 3.0) or 3.0))
    key = launch_visual(bomb, start, end, impact)
    _flights[key]['blast'] = (profile, item)
    call_later(fuse, detonate_flight, key)
    log('local-battle-bomb-thrown', item=item, fuse=round(fuse, 2), at=[round(value, 1) for value in end])
    return True


def detonate_flight(key):
    record = _flights.get(key)
    if record is None or record.get('blast') is None:
        return False
    profile, item = record['blast']
    return detonate(profile, record['pos'], item, key, harmless=record.get('harmless', False))


def use_up_bomb(player, item):
    if not item:
        return False
    try:
        player.onDelDtsFoldedItem(item, 1)
        left = int(player.getDtsItemCnt(item))
    except Exception:
        left = 0
    if left > 0:
        call_later(BOMB_REFILL_DELAY, refill_bomb, player, item)
        return True
    spare = next((prop for prop in BOMB_TYPES if prop != item and carried(player, prop) > 0), None)
    if spare:
        call_later(BOMB_SWAP_DELAY, swap_to_spare, player, item, spare)
    else:
        empty_bomb_slot(player)
    return True


def swap_to_spare(player, spent, spare):
    if int(getattr(player, 'dtsWeapon%d' % BOMB_SLOT, 0) or 0) != spent or carried(player, spare) <= 0:
        return False
    choose_bomb(player, spare)
    tip_text(prop_name(spare))
    return True


BOMB_REFILL_DELAY = 0.2
BOMB_SWAP_DELAY = 0.5
BOMB_TYPES = (1401, 1402, 1403, 1404)


def refill_bomb(player, item):
    if int(getattr(player, 'dtsWeapon%d' % BOMB_SLOT, 0) or 0) != item or carried(player, item) <= 0:
        return False
    bag = weapon_bag(player)
    try:
        magazine = bag.getWeapon(BOMB_SLOT).getCurMagazine()
        missing = int(magazine.magazine_capacity) - int(magazine.bullet_count)
        if missing > 0:
            bag.supplyWeaponMagazine(BOMB_SLOT, item, missing)
        return missing > 0
    except Exception:
        if once('bomb-refill'):
            log_error('local-battle-bomb-refill-error', item=item)
        return False


def ready_bomb(player, item):
    refill_bomb(player, item)
    if getattr(player, 'dtsCurWeapon', None) == BOMB_SLOT:
        try:
            player.doChangeBombWeapon(BOMB_SLOT)
        except Exception:
            switch_weapon(player, BOMB_SLOT)
    return True


def cycle_bomb(player):
    current = int(getattr(player, 'dtsWeapon%d' % BOMB_SLOT, 0) or 0)
    choices = [item for item in BOMB_TYPES if carried(player, item) > 0]
    if not choices:
        return False
    later = [item for item in choices if item > current]
    chosen = later[0] if later else choices[0]
    if chosen == current:
        return False
    equip_slot_item(player, BOMB_SLOT, chosen)
    ready_bomb(player, chosen)
    tip_text(prop_name(chosen))
    return True


def empty_bomb_slot(player):
    weapons = getattr(weapon_bag(player), '_idx2weapon_map', None)
    if isinstance(weapons, dict):
        weapons.pop(BOMB_SLOT, None)
    try:
        setattr(player, 'dtsWeapon%d' % BOMB_SLOT, 0)
        player.onWearDtsWeapon(BOMB_SLOT)
    except Exception:
        if once('bomb-slot-clear'):
            log_error('local-battle-bomb-slot-error')
    try:
        import Globals
        comp = Globals.uiMgr.UIBattlegroundsInGame.GetComponent(WEAPON_BAG_COMP)
        comp.onBombWeaponCountChanged()
        comp.refreshWeaponWidgets()
    except Exception:
        if once('bomb-slot-ui'):
            log_error('local-battle-bomb-slot-ui-error')
    if getattr(player, 'dtsCurWeapon', None) == BOMB_SLOT:
        switch_weapon(player, MELEE_SLOT)
    return True


def on_choose_bomb(player, item=0, *_args, **_kwargs):
    try:
        item = int(item)
    except Exception:
        return None
    if not item or prop_kind(item) != 'PropTypeBombWeapon':
        return None
    left = carried(player, item)
    if int(getattr(player, 'dtsWeapon%d' % BOMB_SLOT, 0) or 0) == item:
        if left > 0:
            refill_bomb(player, item)
    elif left > 0:
        call_later(WEAPON_SWITCH_DELAY, choose_bomb, player, item)
    return None


def choose_bomb(player, item):
    equip_slot_item(player, BOMB_SLOT, item)
    return ready_bomb(player, item)


def carried(player, item):
    try:
        return int(player.getDtsItemCnt(item))
    except Exception:
        return 0


def play_effect(path, point, loop=False):
    if not path:
        return None
    player = current_player()
    physics_module = sys.modules.get('libclaudia.Classes.Physics')
    _effect_ids[0] += 1
    effect_id = _effect_ids[0]
    try:
        x, y, z = point
        player.castSfxAtPosition(physics_module.Vector3(x, y, z), (0.0, 0.0, 0.0), path, effect_id, 1.0, loop)
    except Exception:
        if once('effect-' + path):
            log_error('local-battle-effect-error', path=path)
        return None
    if not loop:
        call_later(ONE_SHOT_LIFE, stop_effect, effect_id)
    return effect_id


def move_effect(effect_id, point):
    player = current_player()
    physics_module = sys.modules.get('libclaudia.Classes.Physics')
    try:
        for effect in list(player.pos_sfx.get(effect_id) or []):
            effect.transform.position = physics_module.Vector3(point[0], point[1], point[2])
        return True
    except Exception:
        return False


def stop_effect(handle):
    if handle is None:
        return False
    if isinstance(handle, (int, long_type)):
        player = current_player()
        try:
            player.stopSfxAtPosition(handle, True)
        except Exception:
            pass
        try:
            player.pos_sfx.pop(handle, None)
        except Exception:
            pass
        return True
    for name in ('Stop', 'stop', 'shutdown'):
        function = getattr(handle, name, None)
        if callable(function):
            try:
                function()
                return True
            except Exception:
                continue
    return False


def play_for(path, point, seconds):
    handle = play_effect(path, point, seconds > 0.0)
    if handle is not None and seconds > 0.0:
        call_later(seconds, stop_effect, handle)
    return handle


def ground_point(point):
    physics_module = sys.modules.get('libclaudia.Classes.Physics')
    ray_module = sys.modules.get('libclaudia.Classes.Ray')
    x, y, z = point
    if physics_module is not None and ray_module is not None:
        try:
            hit = ray_module.RaycastHit()
            if physics_module.Physics.RaycastWithScene(physics_module.Vector3(x, y + GROUND_PROBE, z),
                                                       physics_module.Vector3(0.0, -1.0, 0.0), hit,
                                                       GROUND_PROBE * 4.0):
                return _point(hit.point)
        except Exception:
            pass
    ground = ground_height(x, z)
    return (x, ground if ground else y, z)


_sounds = []


def play_sound(path, point):
    if not path:
        return False
    audio = sys.modules.get('libclaudia.Classes.Audio_')
    physics_module = sys.modules.get('libclaudia.Classes.Physics')
    try:
        clip = audio.AudioClip(path, True)
        clip.Start()
        x, y, z = point
        clip.SetPos(physics_module.Vector3(x, y, z).to_neox_vector())
        _sounds.append(clip)
        del _sounds[:-16]
        return clip
    except Exception:
        if once('sound-' + path):
            log_error('local-battle-sound-error', path=path)
        return None


MODEL_KIT_MODULE = 'DtsPlayerHeritage'
FLIGHT_MODEL_NAME = 'rlThrownBomb'


def model_kit():
    module = sys.modules.get(MODEL_KIT_MODULE)
    if module is None:
        try:
            module = __import__(MODEL_KIT_MODULE)
        except Exception:
            return None
    kit = vars(module)
    needed = ('Application', 'PreCreatedMesh', 'MeshFilter', 'MeshRenderer', 'ResourceController')
    return kit if all(name in kit for name in needed) else None


def throw_velocity(bomb, start, end):
    gravity = float(getattr(bomb, 'GRAVITY', FLIGHT_GRAVITY) or FLIGHT_GRAVITY)
    speed = float(getattr(bomb, 'THROW_SPEED', 250.0) or 250.0)
    angle = math.radians(float(getattr(bomb, 'THROW_ANGLE', 20.0) or 20.0))
    dx, dy, dz = end[0] - start[0], end[1] - start[1], end[2] - start[2]
    reach = math.hypot(dx, dz)
    duration = max(FLIGHT_MIN_TIME, reach / max(1.0, speed * math.cos(angle)))
    return (dx / duration, (dy + 0.5 * gravity * duration * duration) / duration, dz / duration), gravity


def launch_visual(bomb, start, end, impact=False):
    trail = getattr(bomb, 'BOMB_TAIL_SFX', '') or getattr(bomb, 'BOMB_SFX', '')
    _flight_ids[0] += 1
    key = _flight_ids[0]
    velocity, gravity = throw_velocity(bomb, start, end)
    record = {'pos': start, 'vel': velocity, 'gravity': gravity, 'impact': bool(impact), 'clock': time.time(),
              'trail': trail, 'blink': getattr(bomb, 'BOMB_SFX', '') or '', 'go': None,
              'landed': False, 'blast': None, 'touched': False, 'blink_fx': None,
              'hit_sound': getattr(bomb, 'HIT_SOUND', '') or '',
              'touch_sound': getattr(bomb, 'TOUCH_GROUND_SOUND', '') or ''}
    record['trail_fx'] = play_effect(trail, start, True) if trail else None
    _flights[key] = record
    load_flight_model(key, getattr(bomb, 'BOMB_MODEL', '') or '')
    try:
        current_player().behaviour.StartCoroutine(fly_frames(key))
        record['framed'] = True
    except Exception:
        if once('flight-frames'):
            log_error('local-battle-flight-frames-error')
    return key


def fly_frames(key):
    while True:
        record = _flights.get(key)
        if record is None or record.get('landed'):
            return
        step_flight(record, time.time())
        yield None


def load_flight_model(key, path):
    kit = model_kit()
    if not path or kit is None:
        return False

    def loaded(resource):
        record = _flights.get(key)
        try:
            body = kit['Application'].CreateGameObject(FLIGHT_MODEL_NAME)
            body.AddComponent(kit['MeshFilter']).mesh = kit['PreCreatedMesh'](resource)
            body.AddComponent(kit['MeshRenderer']).enabled = True
        except Exception:
            if once('flight-model'):
                log_error('local-battle-flight-model-error', path=path)
            return
        if record is None:
            drop_model(body)
            return
        record['go'] = body
        move_model(body, record['pos'])

    try:
        kit['ResourceController'].g_resource_controller.preload_resource(path, loaded)
        return True
    except Exception:
        if once('flight-model-load'):
            log_error('local-battle-flight-model-load-error', path=path)
        return False


def move_model(body, point):
    physics_module = sys.modules.get('libclaudia.Classes.Physics')
    try:
        body.transform.position = physics_module.Vector3(point[0], point[1], point[2])
        return True
    except Exception:
        return False


def drop_model(body):
    kit = model_kit() or {}
    for destroy in (getattr(kit.get('GameObject'), 'Destroy', None), getattr(body, 'Destroy', None)):
        if callable(destroy):
            try:
                destroy(body)
                return True
            except Exception:
                continue
    return False


def surface_hit(origin, target):
    seg = (target[0] - origin[0], target[1] - origin[1], target[2] - origin[2])
    length = math.sqrt(seg[0] ** 2 + seg[1] ** 2 + seg[2] ** 2)
    if length < 1e-6:
        return None
    physics_module = sys.modules.get('libclaudia.Classes.Physics')
    ray_module = sys.modules.get('libclaudia.Classes.Ray')
    if physics_module is not None and ray_module is not None:
        try:
            hit = ray_module.RaycastHit()
            way = physics_module.Vector3(seg[0] / length, seg[1] / length, seg[2] / length)
            if physics_module.Physics.RaycastWithScene(physics_module.Vector3(*origin), way, hit, length + FLIGHT_SKIN):
                return _point(hit.point), _point(hit.normal)
        except Exception:
            pass
    ground = ground_height(target[0], target[2])
    if ground and target[1] < ground:
        return (target[0], ground, target[2]), (0.0, 1.0, 0.0)
    return None


def move_flights(now=None):
    now = time.time() if now is None else now
    for record in list(_flights.values()):
        if not record.get('landed') and not record.get('framed'):
            step_flight(record, now)


def step_flight(record, now):
    step = min(FLIGHT_MAX_STEP, max(0.0, now - record['clock']))
    record['clock'] = now
    if record.get('landed') or step <= 0.0:
        return
    x, y, z = record['pos']
    vx, vy, vz = record['vel']
    vy -= record['gravity'] * step
    target = (x + vx * step, y + vy * step, z + vz * step)
    contact = surface_hit(record['pos'], target)
    if contact is not None and break_glass(contact[0], contact[1], 'throw') is not None:
        contact = None                          # a window: it shatters and the throw flies on
    if contact is not None:
        point, normal = contact
        bounce_sound(record, point, vx, vy, vz)
        if record['impact']:
            record['pos'] = point
            record['landed'] = True
            stop_effect(record.get('trail_fx'))
            record['trail_fx'] = None
            if record.get('go') is not None:
                move_model(record['go'], point)
            for key, known in list(_flights.items()):
                if known is record:
                    detonate_flight(key)
            return
        along = vx * normal[0] + vy * normal[1] + vz * normal[2]
        vx, vy, vz = [(value - along * axis) * FLIGHT_FRICTION - along * axis * FLIGHT_BOUNCE
                      for value, axis in zip((vx, vy, vz), normal)]
        target = tuple(spot + axis * FLIGHT_SKIN for spot, axis in zip(point, normal))
        if math.sqrt(vx * vx + vy * vy + vz * vz) < FLIGHT_REST_SPEED:
            vx = vy = vz = 0.0
            record['landed'] = True
    record['pos'], record['vel'] = target, (vx, vy, vz)
    if record.get('go') is not None:
        move_model(record['go'], target)
    if record.get('trail_fx') is not None:
        move_effect(record['trail_fx'], target)
    if record['landed']:
        stop_effect(record.get('trail_fx'))
        record['trail_fx'] = None
        record['blink_fx'] = play_effect(record['blink'], target, True)


def bounce_sound(record, point, vx, vy, vz):
    if not record['touched']:
        record['touched'] = True
        play_sound(record['touch_sound'], point)
    if math.sqrt(vx * vx + vy * vy + vz * vz) >= LOUD_BOUNCE:
        play_sound(record['hit_sound'], point)


def end_flight(key):
    record = _flights.pop(key, None) if key is not None else None
    if record is None:
        return False
    if record.get('go') is not None:
        drop_model(record['go'])
    stop_effect(record.get('trail_fx'))
    stop_effect(record.get('blink_fx'))
    return True


def detonate(profile, point, item, visual=None, harmless=False):
    end_flight(visual)
    explode = profile['explode']
    flow = getattr(explode, 'FLOW_CONTROL', None)
    every = float(getattr(flow, 'INTERVAL_TIME', 0.0) or 0.0)
    total = float(getattr(flow, 'TOTAL_TIME', 0.0) or 0.0)
    ticks = int(total / every) if every > 0.0 and total > 0.0 else 1
    floor = ground_point(point)
    lasting = float(getattr(profile['bomb'], 'EXPLODE_TIME', 0.0) or 0.0) if profile['id'] == SMOKE_EXPLODE else 0.0
    play_for(getattr(explode, 'EXPLODE_SFX', ''), floor if lasting else point, lasting)
    play_sound(getattr(explode, 'EXPLODE_SOUND', ''), point)
    for sub in list(getattr(explode, 'EXPLODE_SUB_SFX', None) or []):
        spot = floor if getattr(sub, 'IS_ON_GROUND', False) else point
        play_for(getattr(sub, 'PATH', ''), spot, total)
        clip = play_sound(getattr(sub, 'SOUND_PATH', ''), spot)
        if clip is not None and total > 0.0:
            call_later(total, stop_effect, clip)
    if not harmless:
        blast(profile, point, item)
        for tick in range(1, ticks):
            call_later(every * tick, blast, profile, point, item)
    log('local-battle-bomb-exploded', bomb=profile['id'], at=[round(value, 1) for value in point])
    return True


def band(explode, reach, itself):
    states = sorted(list(getattr(explode, 'EXPLODE_RANGE_STATE_LIST', None) or []),
                    key=lambda state: float(getattr(state, 'RANGE', 0.0) or 0.0))
    for state in states:
        if reach <= float(getattr(state, 'RANGE', 0.0) or 0.0):
            effects = getattr(state, 'EXPLODE_STATE_LIST_ITSELF' if itself else 'EXPLODE_STATE_LIST', None) or []
            hp = 0.0
            statuses = []
            for effect in effects:
                hp += float((getattr(effect, 'PARAMETERS', None) or {}).get('HP', 0.0) or 0.0)
                statuses.extend(list(getattr(effect, 'CLIENT_STATUS', None) or []))
            return hp, statuses
    return 0.0, []


def blast_amount(hp, top):
    return hp * top if 0.0 < hp < 1.0 else hp


def in_blast(explode, point, position):
    reach = math.hypot(position[0] - point[0], position[2] - point[2])
    vertical = float(getattr(getattr(explode, 'EXPLODE_POSITION', None), 'EXPLODE_VERTICAL_RANGE', 0.0) or 0.0)
    if vertical > 0.0 and abs(position[1] - point[1]) > vertical:
        return None
    if reach > float(getattr(explode, 'EXPLODE_RANGE', 0.0) or 0.0):
        return None
    return reach


def blast(profile, point, item):
    player = current_player()
    if player is None:
        return 0
    explode = profile['explode']
    weapon = weapon_record(profile['rail'], profile['rail'], HIT_EXPLODE)
    name = prop_name(item) if item else 'Grenade'
    hit = 0
    for _battle_id, entity in remote_bodies():
        if getattr(entity, 'id', None) in _dead:
            continue
        reach = in_blast(explode, point, _point(entity.position))
        if reach is None:
            continue
        hp, _statuses = band(explode, reach, False)
        amount = blast_amount(hp, float(getattr(entity, 'maxHp', FULL_HP) or FULL_HP))
        if amount > 0.0:
            hurt_avatar(player, entity, amount, point, CHEST_PART, HIT_EXPLODE, weapon, name)
            hit += 1
    if bool(getattr(explode, 'IS_DAMAGE_VEHICLE', False)):
        for entity_id, record in list(_vehicles.items()):
            car = vehicle_entity(entity_id)
            if car is None or record.get('dead'):
                continue
            reach = in_blast(explode, point, _point(car.position))
            if reach is None:
                continue
            hp, _statuses = band(explode, reach, False)
            amount = blast_amount(hp, float(getattr(car, 'maxHp', 1000) or 1000))
            if amount > 0.0:
                damage_vehicle(player, entity_id, amount, point, HIT_EXPLODE, 0, weapon)
                hit += 1
    if bool(getattr(explode, 'IS_DAMAGE_SELF', False)):
        reach = in_blast(explode, point, _point(player.position))
        if reach is not None:
            hp, statuses = band(explode, reach, True)
            hurt_self(player, blast_amount(hp, float(getattr(player, 'maxHp', FULL_HP) or FULL_HP)), point, weapon)
            for status in statuses:
                try:
                    player.skillClientStatusStart(int(status), 0, 0)
                except Exception:
                    if once('status-%s' % status):
                        log_error('local-battle-status-error', status=status)
    return hit


def hurt_self(player, damage, point, weapon):
    amount = int(round(damage))
    if amount <= 0:
        return None
    try:
        old = int(player.hp)
    except Exception:
        return None
    new = max(SELF_MIN_HP, old - amount)
    player.hp = new
    broadcast(player, 'damage', (player.id, point, weapon, amount, new, CHEST_PART, HIT_EXPLODE))
    if new <= 0:
        player_died(player, DEATH_SELF, point)
    changed = getattr(player, 'set_hp', None)
    if callable(changed):
        try:
            changed(old)
        except Exception:
            if once('self-set-hp'):
                log_error('local-battle-self-hp-error')
    return new


def lean_available(self):
    return True


def install_player_methods(entity):
    cls = type(entity)
    installed = []
    for name, function in (('checkLeanAvailable', lean_available),):
        if hasattr(cls, name):
            continue
        try:
            setattr(cls, name, function)
            installed.append(name)
        except Exception:
            pass
    if installed:
        log('local-battle-player-methods', names=installed)
    return installed


def _marker_fields(player):
    """Names on the player that can hold a map marker (ownMarkPos, team marks...),
    found once per body."""
    names = BATTLE['marker_fields']
    if names is None:
        try:
            names = sorted(n for n in dir(player) if 'mark' in n.lower() and not n.startswith('__')
                           and 'market' not in n.lower())
        except Exception:
            names = []
        BATTLE['marker_fields'] = names
        log('local-battle-marker-fields', names=names)
    return names


def _finite_xz(x, z):
    """A removed waypoint is (inf, inf)."""
    x, z = float(x), float(z)
    if math.isinf(x) or math.isinf(z) or math.isnan(x) or math.isnan(z):
        return None
    return x, z


def _as_xz(value):
    """(x, z) from a marker value: (x, y, z), (x, z), a vector, or a list of those."""
    try:
        if hasattr(value, 'x') and hasattr(value, 'z'):
            return _finite_xz(value.x, value.z)
        if hasattr(value, 'x') and hasattr(value, 'y'):
            return _finite_xz(value.x, value.y)     # Vector2(x, z): the map's own form
        items = list(value)
    except Exception:
        return None
    if len(items) in (2, 3) and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                    for v in items):
        return _finite_xz(items[0], items[-1])
    for item in items[:4]:
        found = _as_xz(item)
        if found is not None:
            return found
    return None


MARK_ECHO_DELAY = 0.1


def on_mark_pos(player, position=None, *_args, **_kwargs):
    """player.cell.markPos(Vector2(x, z)) - the big map's waypoint
    (UIDtsMapReal.clickMapCoroutine; Vector2(inf, inf) removes it).

    Online the cell answers the whole team with onTeammateUpdateMarkPosition,
    which is what sets ownMarkPos and the distance on the compass.  Answered a
    moment later, as the network would."""
    if position is None:
        return None
    call_later(MARK_ECHO_DELAY, _echo_mark, player, position)
    return None


def _echo_mark(player, position):
    try:
        player.onTeammateUpdateMarkPosition(player.id, position)
    except Exception:
        log_error('local-battle-mark-echo-failed', mark=safe(position, 120))
        return
    watch_marker()


def watch_marker():
    """Log the player's map marker whenever it moves, with the ground height
    there - the way to find a spawn point the client has no table for (the
    spawn island lives in the server's level data).  Put a waypoint on it in
    the battleground and the log has its exact position.

    Every marker-like field on the body is watched (ownMarkPos is the one the
    replay player sets, but the minimap may keep its waypoint elsewhere)."""
    player = current_player()
    if player is None:
        return None
    found = None
    for name in _marker_fields(player):
        try:
            value = object.__getattribute__(player, name)
        except Exception:
            continue
        if callable(value):
            continue
        xz = _as_xz(value)
        if xz is None or xz == (0.0, 0.0):
            continue
        if BATTLE['markers'].get(name) == xz:
            continue
        BATTLE['markers'][name] = xz
        x, z = xz
        ground = ground_height(x, z)
        spawn = [round(x, 1), round((ground or 0.0) + STAND_HEIGHT, 1), round(z, 1)]
        log('local-battle-marker', map=BATTLE['map'], field=name, mark=[round(x, 1), round(z, 1)],
            ground=ground, spawn=spawn)
        found = spawn
    return found


def _send_input():
    position = _player_position()
    BATTLE['seq'] += 1
    send(INPUT_PREFIX + json.dumps({
        'id': BATTLE['entity_id'],
        'pos': [round(value, 3) for value in position],
        'yaw': round(_player_yaw(), 4),
        'seq': BATTLE['seq'],
        'state': 0,
        'act': my_act(),
        'events': take_outbox(),
        'ev': _relay['seen'],
        'hits': take_hits(),
        'died': take_death(),
        'reborn': take_reborn(),
        'loot_after': _shared.get('loot_seq'),
        'drop_after': _shared.get('drop_seq'),
    }))


def _newest_snapshot():
    """UDP can hand us several ticks at once; only the last one matters, but
    every 'removed' list in between still has to be applied."""
    newest = None
    packets, BATTLE['inbox'] = BATTLE['inbox'] + drain(), []
    for packet in packets:
        # Only snapshots: a join reply (step_ground re-joins) has no tick and
        # no entities, and read as one it would wipe every replicated body.
        if isinstance(packet, dict) and 'tick' not in packet and _chat.get('waiting') \
                and ('action' in packet or 'error' in packet):
            bot_reply(packet)
            continue
        if not isinstance(packet, dict) or not packet.get('ok') or 'tick' not in packet:
            continue
        if int(packet.get('tick') or 0) < BATTLE['tick']:
            continue                    # an old tick overtook a newer one
        for gone in packet.get('removed') or []:
            # the battle host dropped it (quit the round): said before the body
            # goes - destroyed first, it was never seen missing, never announced
            try:
                announce_left(int(gone))
            except Exception:
                if once('left-removed'):
                    log_error('local-battle-left-removed-error')
            _destroy(gone)
        newest = packet
    if newest is not None:
        BATTLE['tick'] = int(newest.get('tick') or 0)
    return newest


def apply_snapshot(snapshot):
    """Draw the world the battle host sent."""
    seen = set()
    for item in snapshot.get('entities') or []:
        try:
            entity_id = int(item.get('id'))
        except Exception:
            continue
        if entity_id in _buried:
            if not (item.get('kind') == 'player' and item.get('alive') is True):
                continue
            _buried.discard(entity_id)          # a player back (an island respawn): a new body
        seen.add(entity_id)
        entity = _remote.get(entity_id)
        if entity is None:
            entity = _spawn_remote(item)
            if entity is None:
                continue
            _remote[entity_id] = entity
        if getattr(_resolve_entity(entity), 'id', entity) in _dead:
            if item.get('alive') is True and item.get('kind') == 'player':
                _dead.discard(getattr(_resolve_entity(entity), 'id', entity))
                _destroy(entity_id)             # it died on the island and is back: drawn anew
                _motion['bodies'].pop(entity_id, None)
            continue
        _kinds[entity_id] = item.get('kind')
        if item.get('kind') == 'player' and item.get('name'):
            _player_names[entity_id] = str(item['name'])
        if item.get('alive') is False:
            remote_died(entity_id, entity, item)       # killed in another game window
            continue
        if item.get('kind') == 'player' and item.get('hp') is not None:
            keep_remote_hp(entity, int(item['hp']))
        push_motion(entity_id, entity, item.get('pos') or (0.0, 0.0, 0.0), item.get('yaw'))
        if item.get('act'):
            apply_act(entity_id, entity, item['act'])
    for entity_id in list(_remote):
        if entity_id not in seen:
            announce_left(entity_id)
            _destroy(entity_id)
    sync_alive_count(snapshot)
    apply_shared_loot(snapshot)
    apply_events(snapshot)
    apply_own_state(snapshot.get('self'))
    if snapshot.get('finished') and BATTLE['phase'] == 'fighting':
        log('local-battle-round-over', tick=snapshot.get('tick'))
        BATTLE['phase'] = 'over'


def remote_properties(item, class_name):
    """What another player's body is made with.  A BattleGroundAvatar gets
    what our own body gets (character, loadout, camp) - without them it has
    no model to dress and nothing to hold."""
    properties = {
        'nickname': str(item.get('name') or 'Player'),
        'ownerID': int(item.get('id') or 0),
        'clientID': int(item.get('id') or 0),
        'nationalFlag': '',
        'occupation': 0,
        'woundCount': 0,
    }
    if class_name == 'ClientTeammate':
        return properties
    properties.update({
        'characterType': int(item.get('character') or DEFAULT_CHARACTER_TYPE),
        'currentMapID': BATTLE['map'],
        'mapID': BATTLE['map'],
        'state_sfx_effect': [],
        'currEquipDtsParagliding': {},
        'preprocessVehicleAppearanceDict': {},
        'abilityDisabled': [0] * ABILITY_COUNT,
        'isObserver': False,
        'isGod': False,
        'hp': FULL_HP,
        'maxHp': FULL_HP,
    })
    properties.update(STARTING_LOADOUT)
    if isinstance(item.get('look'), dict) and item['look']:
        properties.update(look_properties(item['look']))     # another player: their own look
    camp = solo_camp()
    if camp is not None:
        properties['campType'] = camp
    return properties


def install_remote_fallback(class_name):
    """Another player's body reads everything a battle server would have
    sent with it; our own body has the lobby hook's defaults for that
    (local_getattribute), a remote one gets the same answers here.  The
    player itself is left alone: its own lookup already ran and raised."""
    module = sys.modules.get(class_name)
    if module is None:
        try:
            module = __import__(class_name)
        except Exception:
            return False
    cls = getattr(module, class_name, None)
    if not isinstance(cls, type) or cls.__dict__.get('_rl_remote_fallback'):
        return False
    default = getattr(LOBBY, 'battle_player_default', None) if LOBBY is not None else None
    missing = getattr(LOBBY, '_NO_DEFAULT', None) if LOBBY is not None else None
    if not callable(default):
        return False
    previous = cls.__dict__.get('__getattr__')

    def remote_getattr(self, name):
        if previous is not None:
            try:
                return previous(self, name)
            except AttributeError:
                pass
        # Only the plain class: our own body is PlayerBattleGroundAvatar from
        # the moment it is made, and is read during createEntity - before it
        # is BigWorld.player() - so "not the player" cannot be the test.
        if name.startswith('_') or type(self) is not cls or self is current_player():
            raise AttributeError(name)
        value = default(name)
        if value is missing:
            raise AttributeError(name)
        if isinstance(value, (list, dict)):
            # Containers are kept so appends stick.  Nothing else is stored:
            # a declared property converts what it is given (a stand-in
            # became None or 0 - len(None) in iPerspective.perspectCoro).
            try:
                setattr(self, name, value)
            except Exception:
                pass
        return value

    try:
        cls.__getattr__ = remote_getattr
        cls._rl_remote_fallback = True
    except Exception:
        log_error('local-battle-remote-fallback-error', entity_class=class_name)
        return False
    log('local-battle-remote-fallback', entity_class=class_name)
    return True


def _spawn_remote(item):
    """One other player (a bot, offline) as a client entity."""
    position = _point(item.get('pos'))
    names = ((BATTLE['remote_class'],) if BATTLE['remote_class'] else REMOTE_CLASSES)
    for class_name in names:
        if class_name != 'ClientTeammate':
            install_class_defaults(class_name)
            install_remote_fallback(class_name)
        entity = _create_entity(class_name, position, remote_properties(item, class_name))
        if entity is not None:
            if BATTLE['remote_class'] != class_name:
                BATTLE['remote_class'] = class_name
                log('local-battle-remote-class', entity_class=class_name)
            return entity
    if once('remote-class-none'):
        log('local-battle-remote-class-missing', tried=list(REMOTE_CLASSES))
    return None


def _destroy(entity_id):
    try:
        entity_id = int(entity_id)
    except Exception:
        return
    entity = _remote.pop(entity_id, None)
    if entity is None:
        return
    import BigWorld
    for call in ('destroyEntity', 'destroy'):
        function = getattr(BigWorld, call, None)
        if callable(function):
            try:
                function(getattr(entity, 'id', entity))
                return
            except Exception:
                continue
    function = getattr(entity, 'destroy', None)
    if callable(function):
        try:
            function()
        except Exception:
            pass


def _clear_remote():
    for entity_id in list(_remote):
        _destroy(entity_id)
    _remote.clear()
    for entity_id in list(_loot):
        remove_loot(entity_id)
    for entity_id in list(_heritages):
        _heritages.pop(entity_id, None)
        try:
            import BigWorld
            BigWorld.destroyEntity(entity_id)
        except Exception:
            pass
    for entity_id in list(_vehicles):
        _vehicles.pop(entity_id, None)
        try:
            import BigWorld
            BigWorld.destroyEntity(entity_id)
        except Exception:
            pass


# --------------------------------------------------------------------------
# Engine helpers (everything that may not exist in this client build)
# --------------------------------------------------------------------------

def _point(value):
    """(x, y, z) as a plain tuple of floats, from a sequence or a vector."""
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except Exception:
        pass
    try:
        return (float(value.x), float(value.y), float(value.z))
    except Exception:
        return (0.0, 0.0, 0.0)


def map_birth_point(map_id):
    """The map's own spawn, the one the client's scene loader uses
    (``maps_utils.getMapBirthPosition`` in ``SceneSystem.DoLoadNeoxScene``).

    It has to be a point that is really on the map: the teleport that ends a
    map load waits for the landscape around it to stream in
    (``SceneSystem.waitForTerrainReady``), and off the map that never
    finishes - the load sits at stage 2 for ever."""
    try:
        import maps_utils
        value = maps_utils.getMapBirthPosition(int(map_id))
    except Exception as error:
        if once('birth-point'):
            log('local-battle-birth-point-missing', map=map_id,
                error='%s: %s' % (type(error).__name__, error))
        return None
    point = _point(value)
    if point == (0.0, 0.0, 0.0):
        log('local-battle-birth-point-empty', map=map_id, value=safe(value, 80))
        return None
    return point


def _vector3(value):
    """(x, y, z) as whatever vector type this client has."""
    x, y, z = _point(value)
    try:
        import math3d
        return math3d.vector(x, y, z)
    except Exception:
        pass
    try:
        import Math
        return Math.Vector3(x, y, z)
    except Exception:
        return (x, y, z)


def _xyz(value):
    for attribute in ('x', 'y', 'z'):
        if not hasattr(value, attribute):
            try:
                return (float(value[0]), float(value[1]), float(value[2]))
            except Exception:
                return (0.0, 0.0, 0.0)
    return (float(value.x), float(value.y), float(value.z))


def _spawn_point():
    """Where we come into the battleground: the map's own birth position when
    the client knows it, otherwise whatever the battle host said."""
    if BATTLE['spawn'] is not None:
        return BATTLE['spawn']
    return _point((BATTLE['match'] or {}).get('spawn') or (0.0, 0.0, 0.0))


def _space_id():
    try:
        import BigWorld
        player = BigWorld.player()
        return int(getattr(player, 'spaceID', 0) or 0)
    except Exception:
        return 0


def _create_shapes(class_name, space, position, properties):
    """The argument lists to try for createEntity, best first.

    The first one is exactly what ros_local_lobby.create_local_athlete uses
    and that one works in this build: six arguments (class, space, vehicle,
    position, direction, state) with **plain tuples**, not engine vectors.
    Then the same without the properties (an unknown one is refused by some
    entity classes), then the engine-vector form, then the shorter lists
    iBattleGround._createClientTeammate uses."""
    point = tuple(position)
    zero = (0.0, 0.0, 0.0)
    state = dict(properties)
    return (
        ('6-tuple', (class_name, space, 0, point, zero, state)),
        ('6-tuple-bare', (class_name, space, 0, point, zero, {})),
        ('6-vector', (class_name, space, 0, _vector3(point), _vector3(zero), state)),
        ('5-tuple', (class_name, space, point, zero, state)),
        ('4-tuple', (class_name, space, point, state)),
    )


def _resolve_entity(handle):
    """createEntity answers with an entity id in this build (1073741825...);
    everything else wants the object."""
    if handle is None or hasattr(handle, 'position'):
        return handle
    try:
        import BigWorld
        entities = getattr(BigWorld, 'entities', None)
    except Exception:
        return handle
    for lookup in (lambda: entities[handle], lambda: entities.get(handle)):
        try:
            entity = lookup()
        except Exception:
            continue
        if entity is not None:
            return entity
    return handle


def _create_entity(class_name, position, properties):
    """BigWorld.createEntity.  Which argument list this build wants is found
    once and then kept; every failure is logged with its reason, because a
    swallowed one says nothing about why the battleground stayed empty."""
    if not class_name:
        return None
    import BigWorld
    space = BATTLE['space']
    shapes = _create_shapes(class_name, space, position, properties)
    chosen = BATTLE['create_with']
    for name, arguments in shapes:
        if chosen is not None and name != chosen:
            continue
        try:
            entity = BigWorld.createEntity(*arguments)
        except Exception as error:
            if once('create-%s-%s' % (class_name, name)):
                log('local-battle-create-entity-error', entity_class=class_name,
                    shape=name, space=space, args=len(arguments),
                    error='%s: %s' % (type(error).__name__, error))
            continue
        if BATTLE['create_with'] != name:
            BATTLE['create_with'] = name
            log('local-battle-create-with', shape=name, entity_class=class_name)
        return _resolve_entity(entity)
    return None


def describe_engine():
    """One line in the log with what this build offers, the first time the
    battleground is entered: which createEntity/space calls exist and where
    the player is now.  A guess costs a whole run; this costs a line."""
    report = {}
    try:
        import BigWorld
        report['bigworld'] = sorted(name for name in dir(BigWorld)
                                    if 'ntit' in name or 'pace' in name or 'layer' in name
                                    or 'roxy' in name)
        player = BigWorld.player()
        report['player'] = type(player).__name__
        report['space'] = getattr(player, 'spaceID', None)
        entities = getattr(BigWorld, 'entities', None)
        report['entities'] = len(entities) if hasattr(entities, '__len__') else None
    except Exception as error:
        report['error'] = '%s: %s' % (type(error).__name__, error)
    log('local-battle-engine', **report)
    return report


def _place_values(point):
    """A position in each form, best first (see _position_forms)."""
    return (
        ('tuple', tuple(point)),
        ('list', [point[0], point[1], point[2]]),
        ('math3d', _vector3(point)),
        ('Math', _math_vector3(point)),
    )


def _place_ways():
    # Built here, not at import: the three are defined below this function.
    return (('position', _place_position), ('model', _place_model),
            ('teleport', _place_teleport))


def _place(entity, position, yaw=None):
    """Move a replicated entity.  Both the way and the position type that work
    are found once and then kept (they differ per build, and per call)."""
    entity = _resolve_entity(entity)
    if entity is None:
        return False
    point = _point(position)
    chosen_way = BATTLE['place_with']
    chosen_form = BATTLE['position_with'].get('place')
    for form, vector in _place_values(point):
        if chosen_form is not None and form != chosen_form:
            continue
        if vector is None:
            continue
        for name, way in _place_ways():
            if chosen_way is not None and name != chosen_way:
                continue
            try:
                if not way(entity, vector, yaw):
                    continue
            except Exception:
                continue
            if BATTLE['place_with'] != name or chosen_form != form:
                BATTLE['place_with'] = name
                BATTLE['position_with']['place'] = form
                log('local-battle-place-with', how=name, form=form)
            return True
    if once('place-none'):
        log('local-battle-place-failed', entity=safe(entity))
    return False


def _place_position(entity, vector, yaw):
    entity.position = vector
    if yaw is not None:
        try:
            entity.yaw = float(yaw)
        except Exception:
            pass
    return True


def _place_model(entity, vector, yaw):
    model = getattr(entity, 'model', None)
    if model is None:
        return False
    model.position = vector
    if yaw is not None:
        try:
            model.yaw = float(yaw)
        except Exception:
            pass
    return True


def _place_teleport(entity, vector, yaw):
    function = getattr(entity, 'teleport', None)
    if not callable(function):
        return False
    function(vector)
    return True


def _map_loader():
    try:
        from helpers.MapLoader import MapLoader
        return MapLoader.getInstance()
    except Exception:
        try:
            import MapLoader
            return MapLoader.MapLoader.getInstance()
        except Exception:
            if once('map-loader'):
                log('local-battle-map-loader-missing')
            return None


def _scene_system():
    """GameObject.Find('Scene').GetComponent('SceneSystem'), as MapLoader does."""
    try:
        import libclaudia
        scene = libclaudia.GameObject.Find('Scene')
        return scene.GetComponent('SceneSystem')
    except Exception:
        try:
            from libclaudia import GameObject
            return GameObject.Find('Scene').GetComponent('SceneSystem')
        except Exception:
            if once('scene-system'):
                log('local-battle-scene-system-missing')
            return None


def _player_position():
    try:
        import BigWorld
        return _xyz(BigWorld.player().position)
    except Exception:
        return _spawn_point()


def _player_yaw():
    try:
        import BigWorld
        return float(getattr(BigWorld.player(), 'yaw', 0.0) or 0.0)
    except Exception:
        return 0.0


def distance(first, second):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))


# --------------------------------------------------------------------------
# Chat commands in battle: "/spawn bot 3", "/hp 40"...  Anything else (and
# the lobby's own /gp, /item...) still goes to the backend's chat server.
# --------------------------------------------------------------------------

CHAT_SYSTEM_NAME = 'DieHard ROS'
CHAT_SYSTEM_GID = 1
# onChat unpickles params['info']; this is pickle protocol 0 for {}.
CHAT_EMPTY_INFO = '(dp0\n.'
BOT_SPAWN_AHEAD = 100.0
BOT_SPAWN_RADIUS = 50.0
MAX_CHAT_BOTS = 30
MAX_CHAT_ITEMS = 999
CHAT_AMMO = 120
CAR_SPAWN_AHEAD = 120.0
THROWABLE_COUNT = 5
MED_KIT = ((101, 5), (102, 3), (103, 2), (104, 1), (105, 3))
HEALER_AMMO_COUNT = 5
ITEM_ALIASES = {
    'grenade': 1401, 'frag': 1401, 'stun': 1402, 'flash': 1402, 'smoke': 1403,
    'molotov': 1404, 'molly': 1404, 'bandage': 101, 'medkit': 102, 'firstaid': 103,
    'baterbonia': 104, 'drink': 105, 'healer': HEALER_GUN, 'healerammo': HEALER_AMMO,
}
ITEM_SCAN = (range(1, 30), range(100, 130), range(1000, 1130), range(1200, 1310),
             range(1400, 1410), range(90050, 90052))
CHAT_HELP = (
    'Battle commands:',
    '/spawn bot [n] [still] - bots in front of you',
    '/spawn car | loot | throwables | meds | healer | ammo',
    '/spawn <item id or name> [n] - e.g. /spawn awm, /spawn 1401 5',
    '/bots clear | freeze | walk | speed <n> | count',
    '/hp <n> - set your HP, /heal - full HP',
    '/jump [times] - jump higher (default 3x, max 50x), /jump off',
    '/fly [speed] - noclip: look and hold W to fly through walls, /fly off',
    'Lobby commands (/gp, /item...) still work.',
)
CHAT_HELP_TIP = 'Commands listed in Chat history'
_chat = {'channel': 0, 'waiting': 0}
_item_names = {}


def install_chat_commands(player):
    cls = type(player) if player is not None else None
    if cls is None:
        return False
    if cls.__dict__.get('_rl_chat_commands'):
        return True
    original = getattr(cls, 'chat', None)
    if original is None:
        return False

    def chat(self, channel, msg, *args, **kwargs):
        try:
            if chat_command(self, channel, msg):
                return None
        except Exception:
            log_error('local-battle-chat-command-error')
            return None
        return original(self, channel, msg, *args, **kwargs)

    try:
        cls.chat = chat
        cls._rl_chat_commands = True
    except Exception:
        log_error('local-battle-chat-hook-error')
        return False
    return True


def chat_text(msg):
    if isinstance(msg, bytes) and not isinstance(msg, str):
        return msg.decode('utf-8', 'replace')
    try:
        return msg if isinstance(msg, str) else str(msg)
    except Exception:
        return ''


def chat_command(player, channel, msg):
    text = chat_text(msg).strip()
    if not text.startswith('/') or BATTLE.get('phase') != 'fighting':
        return False
    parts = text[1:].split()
    handler = CHAT_COMMANDS.get(parts[0].lower()) if parts else None
    if handler is None:
        return False
    _chat['channel'] = channel
    chat_say(player, text, avatar_name(player), int(getattr(player, 'gid', 0) or 0))
    answer = handler(player, [part.lower() for part in parts[1:]])
    lines = [answer] if isinstance(answer, str) else list(answer or ())
    for line in lines:
        chat_say(player, line)
    if len(lines) == 1:
        tip_text(lines[0])
    elif lines:
        tip_text(CHAT_HELP_TIP)
    log('local-battle-chat-command', text=text)
    return True


def chat_say(player, text, name=CHAT_SYSTEM_NAME, gid=None):
    # The mini chat on screen only shows lines from you or a teammate.
    if gid is None:
        gid = int(getattr(player, 'gid', 0) or 0) or CHAT_SYSTEM_GID
    sender = {'id': gid, 'name': name, 'nationalFlag': ''}
    params = {'is_voice': False, 'info': CHAT_EMPTY_INFO, 'character': 0}
    try:
        player.onChat(_chat['channel'], text, sender, params)
        return True
    except Exception:
        if once('chat-say'):
            log_error('local-battle-chat-say-error')
    tip_text(text)
    return False


def chat_count(args, index, default, top):
    try:
        value = int(args[index])
    except (IndexError, ValueError, TypeError):
        return default
    return max(1, min(top, value))


def point_ahead(player, distance_ahead):
    position = player.position
    yaw = float(getattr(player, 'yaw', 0.0) or 0.0)
    return (position.x + distance_ahead * math.sin(yaw), position.y,
            position.z + distance_ahead * math.cos(yaw))


def cmd_help(player, args):
    return CHAT_HELP


def cmd_spawn(player, args):
    if not args:
        return 'Usage: /spawn bot [n] | car | loot | throwables | meds | healer | ammo | <item> [n]'
    what = args[0]
    if what in ('bot', 'bots'):
        return spawn_bots(player, chat_count(args, 1, 1, MAX_CHAT_BOTS), 'still' in args[1:] or 'freeze' in args[1:])
    if what in ('car', 'vehicle'):
        return spawn_car(player)
    if what == 'loot':
        return spawn_loot_here(player)
    if what in ('throwables', 'nades', 'bombs'):
        count = chat_count(args, 1, THROWABLE_COUNT, MAX_CHAT_ITEMS)
        for item in BOMB_TYPES:
            grant_prop(player, item, count)
        return 'Added %d of each throwable.' % count
    if what in ('meds', 'heals', 'aid'):
        for item, count in MED_KIT:
            grant_prop(player, item, count)
        return 'Added bandages, med kits, first aid, a Baterbonia Kit and drinks.'
    if what == 'healer' and len(args) == 1:
        grant_prop(player, HEALER_GUN, 1)
        add_item(player, HEALER_AMMO, HEALER_AMMO_COUNT)
        return 'Healer equipped with %d spare ammo.' % HEALER_AMMO_COUNT
    if what == 'ammo':
        return spawn_ammo(player)
    return spawn_item(player, what, chat_count(args, 1, 1, MAX_CHAT_ITEMS))


def spawn_bots(player, count, still):
    if not send(BOT_PREFIX + json.dumps({'action': 'spawn', 'count': count, 'still': bool(still),
                                         'pos': list(point_ahead(player, BOT_SPAWN_AHEAD)),
                                         'radius': BOT_SPAWN_RADIUS})):
        return 'The battle host is not reachable.'
    _chat['waiting'] += 1
    return 'Spawning %d %sbot%s...' % (count, 'standing ' if still else '', '' if count == 1 else 's')


def bot_command(action, **extra):
    request = {'action': action}
    request.update(extra)
    if not send(BOT_PREFIX + json.dumps(request)):
        return 'The battle host is not reachable.'
    _chat['waiting'] += 1
    return None


def cmd_bots(player, args):
    action = args[0] if args else 'count'
    if action in ('clear', 'remove', 'kill'):
        return bot_command('clear')
    if action in ('freeze', 'still', 'stop'):
        return bot_command('freeze')
    if action in ('walk', 'move', 'go'):
        return bot_command('walk')
    if action == 'speed':
        try:
            return bot_command('speed', value=float(args[1]))
        except (IndexError, ValueError):
            return 'Usage: /bots speed <n> (0 stops them, default 4)'
    if action == 'count':
        return bot_command('count')
    return 'Usage: /bots clear | freeze | walk | speed <n> | count'


def bot_reply(packet):
    _chat['waiting'] = max(0, _chat['waiting'] - 1)
    player = current_player()
    if not packet.get('ok'):
        text = 'Bots: %s' % packet.get('error', 'failed')
    else:
        action = packet.get('action')
        alive, total = int(packet.get('alive') or 0), int(packet.get('total') or 0)
        if action == 'spawn':
            text = 'Spawned %d bot(s). Bots alive: %d' % (len(packet.get('made') or ()), alive)
        elif action == 'clear':
            text = 'Removed %d bot(s).' % int(packet.get('cleared') or 0)
        elif action == 'speed':
            text = 'Bot speed is now %s.' % packet.get('speed')
        elif action == 'freeze':
            text = 'Bots stand still (%d).' % total
        elif action == 'walk':
            text = 'Bots walk again (%d).' % total
        else:
            text = 'Bots alive: %d of %d' % (alive, total)
        set_alive_count(alive + 1)
    if player is not None:
        chat_say(player, text)
        tip_text(text)
    return text


def set_alive_count(value):
    try:
        import Globals
        space = Globals.spaceEntity
    except Exception:
        return False
    if space is None:
        return False
    old = int(getattr(space, 'aliveNum', 0) or 0)
    return bump(space, 'aliveNum', int(value) - old, floor=1)


def spawn_car(player):
    x, _y, z = point_ahead(player, CAR_SPAWN_AHEAD)
    ground = surface_clear(x, z)
    if ground is None:
        return 'No flat ground in front of you for a car.'
    import random
    class_name, land, tps = random.choice(VEHICLE_FLEET)
    if spawn_own_car(class_name, land, tps, x, z, ground, float(getattr(player, 'yaw', 0.0) or 0.0)) is None:
        return 'The car could not be made.'
    return 'A car is waiting in front of you.'


def spawn_own_car(class_name, land, tps, x, z, ground, yaw):
    """A car only this window places (a chat /spawn, the cars put down around
    a landing): made here and sent to the others, the same car with the same
    key, so it can be driven and ridden together."""
    car_id = spawn_vehicle(class_name, land, tps, x, z, ground, yaw)
    if car_id is None:
        return None
    _shared['cars'] = int(_shared.get('cars') or 0) + 1
    key = 'q%s-%d' % (BATTLE.get('entity_id') or 0, _shared['cars'])
    share_car(car_id, key)
    emit('car', {'key': key, 'class': class_name, 'land': int(land), 'tps': int(tps),
                 'pos': [round(x, 2), round(ground, 2), round(z, 2)], 'yaw': round(float(yaw), 4)})
    return car_id


def spawn_loot_here(player):
    import random
    position = player.position
    plan = loot_plan((position.x, position.z), random.Random())
    scatter_loot(plan)
    return 'Loot scattered around you (%d items).' % len(plan)


def spawn_ammo(player):
    added = []
    for slot in GUN_SLOTS + (PISTOL_SLOT,):
        try:
            gun = int(getattr(player, 'dtsWeapon%d' % slot)['weaponID'] or 0)
        except Exception:
            continue
        bullet = gun_bullet(gun) if gun else 0
        if bullet and bullet not in added:
            add_item(player, bullet, HEALER_AMMO_COUNT if gun == HEALER_GUN else CHAT_AMMO)
            added.append(bullet)
    if not added:
        return 'You have no guns to load.'
    return 'Ammo added for %d gun(s).' % len(added)


def spawn_item(player, name, count):
    prop = resolve_item(name)
    if not prop:
        return 'Unknown item "%s". Use an item id or a name like awm, grenade, bandage.' % name
    kind = grant_prop(player, prop, count)
    if not kind:
        return 'Item %d is not a battle item.' % prop
    if kind == 'PropTypeGun':
        bullet = gun_bullet(prop)
        if bullet:
            add_item(player, bullet, HEALER_AMMO_COUNT if prop == HEALER_GUN else CHAT_AMMO)
        return 'Equipped %s.' % prop_name(prop)
    return 'Added %s x%d.' % (prop_name(prop), count)


def squash(text):
    return re.sub(r'[^a-z0-9+]', '', str(text).lower())


def resolve_item(name):
    if str(name).isdigit():
        return int(name) if prop_kind(int(name)) else 0
    key = squash(name)
    if key in ITEM_ALIASES:
        return ITEM_ALIASES[key]
    if not _item_names:
        for block in ITEM_SCAN:
            for prop in block:
                if prop_kind(prop):
                    _item_names.setdefault(squash(prop_name(prop)), prop)
    if key in _item_names:
        return _item_names[key]
    starts = sorted(prop for label, prop in _item_names.items() if label.startswith(key))
    if starts:
        return starts[0]
    inside = sorted(prop for label, prop in _item_names.items() if key and key in label)
    return inside[0] if inside else 0


def cmd_hp(player, args):
    try:
        top = int(getattr(player, 'maxHp', 0) or 100)
        value = max(1, min(top, int(args[0])))
    except (IndexError, ValueError, TypeError):
        return 'Usage: /hp <1-100>'
    old = int(getattr(player, 'hp', 0) or 0)
    player.hp = value
    try:
        player.set_hp(old)
    except Exception:
        pass
    return 'HP set to %d.' % value


JUMP_DEFAULT_FACTOR = 3.0
JUMP_MAX_FACTOR = 50.0
JUMP_NORMAL_HEIGHT = 20.0
JUMP_OFF = ('off', 'reset', 'normal', 'stop', '0', '1')


def move_unit(player):
    try:
        return player.gameObject.GetComponent('MoveUnit')
    except Exception:
        return None


def normal_jump_height(unit):
    try:
        return float(unit.characterParams.maxJumpHeight) or JUMP_NORMAL_HEIGHT
    except Exception:
        return JUMP_NORMAL_HEIGHT


def cmd_jump(player, args):
    unit = move_unit(player)
    if unit is None:
        return 'You cannot jump right now.'
    if args and args[0] in JUMP_OFF:
        unit.onStopJumpBuff()
        return 'Jump is back to normal.'
    try:
        factor = float(args[0]) if args else JUMP_DEFAULT_FACTOR
    except ValueError:
        return 'Usage: /jump <times higher, e.g. 5> or /jump off'
    factor = max(1.0, min(JUMP_MAX_FACTOR, factor))
    height = normal_jump_height(unit) * factor
    unit.onStartJumpBuff(height)
    return 'Jump boosted x%g (about %d m). /jump off to stop.' % (factor, int(round(height / 10.0)))


FLY_DEFAULT_SPEED = 150.0
FLY_MAX_SPEED = 2000.0
FLY_MAX_FRAME = 0.1
FLY_LAND_LIFT = 1.0
FLY_OFF = ('off', 'stop', 'land', 'normal')
_noclip = {'on': False, 'token': 0}


def cmd_fly(player, args):
    if args and args[0] in FLY_OFF:
        return stop_noclip(player)
    try:
        speed = float(args[0]) if args else FLY_DEFAULT_SPEED
    except ValueError:
        return 'Usage: /fly [speed, default 150] or /fly off'
    speed = max(1.0, min(FLY_MAX_SPEED, speed))
    if _noclip.get('on'):
        _noclip['speed'] = speed
        return 'Fly speed %d.' % int(speed)
    return start_noclip(player, speed)


def start_noclip(player, speed):
    unit = move_unit(player)
    try:
        character = unit.character
        start = _point(character.position)
        character.setGravity(0.0)
        character.setFallSpeed(0.0)
        character.verticalVelocity = 0.0
    except Exception:
        log_error('local-battle-fly-error')
        return 'You cannot fly right now.'
    _noclip['token'] += 1
    _noclip.update(on=True, speed=speed, pos=start)
    try:
        player.behaviour.StartCoroutine(noclip_frames(unit, _noclip['token']))
    except Exception:
        log_error('local-battle-fly-error')
        stop_noclip(player)
        return 'You cannot fly right now.'
    return 'Noclip on (speed %d): look where you want to go and hold W. /fly off to land.' % int(speed)


def stop_noclip(player):
    if not _noclip.get('on'):
        return 'You are not flying.'
    _noclip['on'] = False
    unit = move_unit(player)
    try:
        params = unit.characterParams
        unit.character.setGravity(float(params.gravity))
        unit.character.setFallSpeed(float(params.maxFallSpeed))
    except Exception:
        log_error('local-battle-fly-error')
    try:
        x, y, z = _point(player.position)
        surface = surface_below(x, z, y)
        if surface is not None:
            land_player(player, (x, surface + FLY_LAND_LIFT, z))
        unit.clearJumpAndFallState()
    except Exception:
        pass
    return 'Noclip off, landed.'


def noclip_frames(unit, token):
    last = time.time()
    while _noclip.get('on') and _noclip.get('token') == token:
        yield None
        now = time.time()
        frame, last = min(FLY_MAX_FRAME, now - last), now
        try:
            fly_step(unit, frame)
        except Exception:
            if once('fly-step'):
                log_error('local-battle-fly-step-error')


def camera_axes():
    camera = getattr(sys.modules.get('libclaudia.Classes.Camera'), 'Camera', None)
    transform = camera.main.transform
    return _point(transform.forward), _point(transform.right)


def fly_direction(walk, forward, right):
    """WASD (the walk direction, flat) turned into a 3D flight direction
    along the camera: W while looking up climbs."""
    wx, wz = walk[0], walk[2]
    size = math.hypot(wx, wz)
    if size < 1e-4:
        return (0.0, 0.0, 0.0)
    wx, wz = wx / size, wz / size
    flat_f = math.hypot(forward[0], forward[2]) or 1.0
    flat_r = math.hypot(right[0], right[2]) or 1.0
    ahead = wx * forward[0] / flat_f + wz * forward[2] / flat_f
    side = wx * right[0] / flat_r + wz * right[2] / flat_r
    move = [ahead * forward[i] + side * right[i] for i in range(3)]
    length = math.sqrt(sum(value * value for value in move)) or 1.0
    return tuple(value / length for value in move)


def fly_step(unit, frame):
    character = unit.character
    forward, right = camera_axes()
    direction = fly_direction(_point(character.getWalkDirection()), forward, right)
    step = _noclip['speed'] * frame
    x, y, z = _noclip['pos']
    target = (x + direction[0] * step, y + direction[1] * step, z + direction[2] * step)
    _noclip['pos'] = target
    character.verticalVelocity = 0.0
    character.position = type(character.position)(*target)
    return target


def cmd_heal(player, args):
    return cmd_hp(player, [str(int(getattr(player, 'maxHp', 100) or 100))])


CHAT_COMMANDS = {
    'help': cmd_help, 'commands': cmd_help,
    'spawn': cmd_spawn, 'give': cmd_spawn,
    'bots': cmd_bots, 'bot': lambda player, args: cmd_spawn(player, ['bot'] + list(args)),
    'hp': cmd_hp, 'heal': cmd_heal,
    'jump': cmd_jump,
    'fly': cmd_fly, 'noclip': cmd_fly,
}


# --------------------------------------------------------------------------
# The safe zone and the red (bombing) zone, run from the map's own battle
# parameters (map 700: BATTLE_GROUND_PARAM 799), the way the server did:
# the first white circle (the next safe zone) shows up FIRST_WHITE_CIRCLE_TIME
# after the fight starts; each round waits PREPARE_TIME, then the blue circle
# (the edge of the poison) shrinks onto the white one over SCALE_TIME.
# Outside the blue circle: DAMAGE every INTERVAL seconds.
# --------------------------------------------------------------------------

ZONE_TICK = 0.5
ZONE_FIGHT_STATUS = 3                   # BattleGroundGameStatusEnum.FIGHT
ZONE_REDRAW = 1.0                       # a radius change smaller than this is not sent
RED_ZONE_DAMAGE = 60
RED_ZONE_MIN_BLUE = 3000.0
RED_ZONE_DROPS_PER_TICK = 3              # no more red zones once the safe zone is this small
ZONE_POISON = 'isInPoisonArea'
# const.DTS_INFIGHT_TIPS: the HUD banners the server used to send
ZONE_SCALE_MESSAGE = 4                  # CIRCLE_SCALE: "Restricting safe zone"
ZONE_SHRINK_IN_MINUTES = 6              # SAFE_ZONE_FORMAT1
ZONE_SHRINK_IN_SECONDS = 7              # SAFE_ZONE_FORMAT2
ZONE_SHRINK_IN_TIME = 0                 # SAFE_ZONE: minutes and seconds
ZONE_REMINDERS = (180, 120, 60, 30)
ZONE_TIPS = {
    'white': 'New safe zone! It closes in %s',
    'remind': 'The safe zone closes in %s',
    'shrink': 'The safe zone is closing in!',
    'final': 'Final safe zone',
    'red': 'Red zone! Bombing starts in %ds',
    'red_on': 'The red zone is being bombed!',
    'red_off': 'The red zone is clear',
}
_zone = {'on': False, 'token': 0}


def zone_config():
    module = _properties_module()
    try:
        data = _map_record(BATTLE.get('map'))
        return module.getBattleGroundParamData(int(data.BATTLE_GROUND_PARAM))
    except Exception:
        log_error('local-battle-zone-config-error')
        return None


def zone_rounds(config):
    rounds = []
    for item in list(getattr(config, 'CIRCLE_PARAM', None) or []):
        rounds.append({
            'radius': float(getattr(item, 'RADIUS', 0) or 0),
            'prepare': float(getattr(item, 'PREPARE_TIME', 0) or 0),
            'scale': float(getattr(item, 'SCALE_TIME', 0) or 0),
            'damage': float(getattr(item, 'DAMAGE', 0) or 0),
            'interval': float(getattr(item, 'INTERVAL', 1.0) or 1.0),
            'remind': sorted(float(value) for value in (getattr(item, 'REMIND_TIME', None) or [])),
            'box': tuple(float(value) for value in (getattr(item, 'SINGLE_CIRCLE_BOUND_BOX', None) or ())),
        })
    return rounds


def zone_start_circle(config):
    x, z = (list(getattr(config, 'INIT_BLUE_CIRCLE_POSITION', None) or [0.0, 0.0]) + [0.0, 0.0])[:2]
    return (float(x), float(z), float(getattr(config, 'INIT_BLUE_CIRCLE_RADIUS', 0) or 0))


def plan_circles(start, rounds, randomizer, first_center=None):
    """Where every white circle goes: each inside the one before (so the
    blue circle can close onto it), kept in that round's bound box."""
    circles = []
    cx, cz, radius = start
    for index, round_info in enumerate(rounds):
        new_radius = round_info['radius']
        room = max(0.0, radius - new_radius)
        if index == 0 and first_center is not None:
            x, z = first_center
            offset = math.hypot(x - cx, z - cz)
            if offset > room and offset > 0.0:
                x, z = cx + (x - cx) * room / offset, cz + (z - cz) * room / offset
        else:
            angle = randomizer.uniform(0.0, 2.0 * math.pi)
            distance = room * math.sqrt(randomizer.random())
            x, z = cx + distance * math.cos(angle), cz + distance * math.sin(angle)
        box = round_info['box']
        if len(box) == 4:
            x = min(max(x, box[0]), box[2])
            z = min(max(z, box[1]), box[3])
            # the clamp may push it out of the old circle: pull it back in
            offset = math.hypot(x - cx, z - cz)
            if offset > room and offset > 0.0:
                x, z = cx + (x - cx) * room / offset, cz + (z - cz) * room / offset
        circles.append((x, z, new_radius))
        cx, cz, radius = x, z, new_radius
    return circles


def zone_timeline(config, rounds):
    """(appear, shrink starts, shrink ends) for every round, in zone seconds."""
    times = []
    moment = float(getattr(config, 'FIRST_WHITE_CIRCLE_TIME', 0) or 0)
    for round_info in rounds:
        shrink = moment + round_info['prepare']
        end = shrink + round_info['scale']
        times.append((moment, shrink, end))
        moment = end
    return times


def zone_state(start, circles, times, rounds, elapsed):
    """The circles at ``elapsed`` zone seconds."""
    blue = start
    for index, (appear, shrink, end) in enumerate(times):
        if elapsed < appear:
            return {'stage': index, 'phase': 'wait', 'blue': blue, 'white': None,
                    'rest': appear - elapsed, 'round': None, 'from': blue}
        target = circles[index]
        if elapsed < shrink:
            return {'stage': index + 1, 'phase': 'wait', 'blue': blue, 'white': target,
                    'rest': shrink - elapsed, 'round': rounds[index], 'from': blue}
        if elapsed < end:
            share = (elapsed - shrink) / max(1e-6, end - shrink)
            moving = tuple(blue[axis] + (target[axis] - blue[axis]) * share for axis in range(3))
            return {'stage': index + 1, 'phase': 'shrink', 'blue': moving, 'white': target,
                    'rest': end - elapsed, 'round': rounds[index], 'from': blue}
        blue = target
    last = rounds[-1] if rounds else None
    return {'stage': len(times), 'phase': 'done', 'blue': blue, 'white': blue, 'rest': 0.0,
            'round': last, 'from': blue}


def start_zone(first_center=None, speed=None):
    config = zone_config()
    rounds = zone_rounds(config) if config is not None else []
    if not rounds:
        return False
    import random
    randomizer = random.Random(match_uuid() + '-zone-%d' % _zone['token'])
    start = zone_start_circle(config)
    _zone['token'] += 1
    _zone.update(on=True, config=config, rounds=rounds, start=start,
                 circles=plan_circles(start, rounds, randomizer, first_center),
                 times=zone_timeline(config, rounds), elapsed=0.0, clock=time.time(),
                 speed=float(speed or _zone.get('speed') or 1.0), shown={}, reminded=set(),
                 hurt_at=0.0, poisoned=False, bomb=new_bomb_plan(config), random=randomizer,
                 last_stage=-1, last_phase=None)
    set_fight_status()
    call_later(ZONE_TICK, zone_tick, _zone['token'])
    log('local-battle-zone-start', rounds=len(rounds), first=[round(v) for v in _zone['circles'][0]])
    return True


def stop_zone():
    _zone['on'] = False
    _zone['token'] += 1
    player = current_player()
    if player is not None:
        set_poisoned(player, False)
    end_red_zone()
    return True


def set_fight_status():
    space = zone_space()
    if space is None or _flight.get('stage') == 'plane':
        return False                    # the plane flies in BEFORE_FIGHT; end_plane sets FIGHT
    return set_space_field(space, 'gameStatus', ZONE_FIGHT_STATUS)


def zone_tick(token):
    if not _zone.get('on') or _zone.get('token') != token:
        return False
    if BATTLE.get('phase') != 'fighting':
        _zone['on'] = False
        return False
    now = time.time()
    _zone['elapsed'] += (now - _zone['clock']) * _zone['speed']
    _zone['clock'] = now
    try:
        state = zone_state(_zone['start'], _zone['circles'], _zone['times'], _zone['rounds'], _zone['elapsed'])
        show_zone(state)
        zone_messages(state)
        poison_player(state)
        run_red_zone(state)
    except Exception:
        if once('zone-tick'):
            log_error('local-battle-zone-error')
    call_later(ZONE_TICK, zone_tick, token)
    return True


def zone_space():
    try:
        import Globals
        return Globals.spaceEntity
    except Exception:
        return None


def vector2(space, x, z):
    kind = type(getattr(space, 'blueCircleCenter', None))
    if kind.__name__ != 'Vector2':
        kind = getattr(sys.modules.get('Math'), 'Vector2', None)
    if kind is None:
        return (x, z)
    return kind(float(x), float(z))


def set_space_field(space, name, value, setter=True):
    old = getattr(space, name, None)
    try:
        setattr(space, name, value)
    except Exception:
        if once('zone-field-' + name):
            log_error('local-battle-zone-field-error', name=name)
        return False
    changed = getattr(space, 'set_' + name, None) if setter else None
    if callable(changed):
        try:
            changed(old)
        except Exception:
            if once('zone-setter-' + name):
                log_error('local-battle-zone-setter-error', name=name)
    return True


def circle_changed(shown, key, circle):
    previous = shown.get(key)
    if previous is not None and all(abs(previous[axis] - circle[axis]) < ZONE_REDRAW for axis in range(3)):
        return False
    shown[key] = circle
    return True


def show_zone(state):
    space = zone_space()
    if space is None:
        return False
    shown = _zone['shown']
    if shown.get('stage') != state['stage']:
        shown['stage'] = state['stage']
        set_space_field(space, 'circleStage', state['stage'])
    white = state['white']
    if white is not None and circle_changed(shown, 'white', white):
        set_space_field(space, 'whiteCircleCenter', vector2(space, white[0], white[1]))
        set_space_field(space, 'whiteCircleRadius', white[2])
        redraw_map()
    start = state['from']
    if circle_changed(shown, 'from', start):
        set_space_field(space, 'blueCircleStartCenter', vector2(space, start[0], start[1]), False)
        set_space_field(space, 'blueCircleStartRadius', start[2], False)
    blue = state['blue']
    if circle_changed(shown, 'blue', blue):
        set_space_field(space, 'blueCircleCenter', vector2(space, blue[0], blue[1]), False)
        set_space_field(space, 'blueCircleRadius', blue[2])
    rest = int(math.ceil(state['rest']))
    if shown.get('rest') != rest:
        shown['rest'] = rest
        try:
            space.updateCircleRestTime(rest)
        except Exception:
            if once('zone-rest'):
                log_error('local-battle-zone-rest-error')
    return True


def redraw_map():
    try:
        import Globals
        ui = getattr(Globals.uiMgr, 'UIDtsMap', None)
        redraw = getattr(ui, '_redrawCircle', None)
        if callable(redraw):
            redraw()
    except Exception:
        pass


def clock_text(seconds):
    seconds = max(0, int(round(seconds)))
    return '%d:%02d' % (seconds // 60, seconds % 60)


def zone_notify(text):
    space = zone_space()
    try:
        space.showCircleNotify(text)
    except Exception:
        tip_text(text)
    return text


def zone_banner(message, seconds=0):
    """The HUD's own safe-zone banner (UIPanelMain._fadeSafeZone): it turns the
    seconds into its "N minutes" / "N seconds" text itself."""
    space = zone_space()
    try:
        space.showCircleMessage(message, int(seconds))
        return True
    except Exception:
        if once('zone-banner'):
            log_error('local-battle-zone-banner-error')
        return False


def shrink_banner(rest):
    rest = int(math.floor(rest + 0.5))
    if rest < 60:
        return zone_banner(ZONE_SHRINK_IN_SECONDS, rest)
    if rest % 60 == 0:
        return zone_banner(ZONE_SHRINK_IN_MINUTES, rest)
    return zone_banner(ZONE_SHRINK_IN_TIME, rest)


def zone_messages(state):
    key = (state['stage'], state['phase'])
    if key != (_zone['last_stage'], _zone['last_phase']):
        _zone['last_stage'], _zone['last_phase'] = key
        if state['phase'] == 'wait' and state['white'] is not None:
            shrink_banner(state['rest'])
            send_bot_zone(state['white'])
            for mark in ZONE_REMINDERS:          # no reminder for a moment already gone
                if mark >= state['rest'] - 1.0:
                    _zone['reminded'].add((state['stage'], mark))
        elif state['phase'] == 'shrink':
            zone_banner(ZONE_SCALE_MESSAGE)
    if state['phase'] == 'wait' and state['white'] is not None:
        for mark in ZONE_REMINDERS:
            tag = (state['stage'], mark)
            if state['rest'] <= mark and tag not in _zone['reminded']:
                _zone['reminded'].add(tag)
                shrink_banner(mark)


def send_bot_zone(circle):
    return send(BOT_PREFIX + json.dumps({'action': 'zone', 'center': [circle[0], circle[1]],
                                         'radius': circle[2]}))


def outside_circle(point, circle):
    return math.hypot(point[0] - circle[0], point[2] - circle[1]) > circle[2]


def set_poisoned(player, poisoned):
    if bool(getattr(player, ZONE_POISON, False)) == bool(poisoned):
        return False
    old = getattr(player, ZONE_POISON, False)
    try:
        setattr(player, ZONE_POISON, bool(poisoned))
        player.set_isInPoisonArea(old)
    except Exception:
        if once('zone-poison'):
            log_error('local-battle-zone-poison-error')
    return True


def poison_player(state):
    player = current_player()
    if player is None:
        return False
    try:
        point = _point(player.position)
    except Exception:
        return False
    outside = outside_circle(point, state['blue'])
    set_poisoned(player, outside)
    if not outside:
        _zone['hurt_at'] = 0.0
        return False
    round_info = state['round']
    if round_info is None:
        damage = float(getattr(_zone['config'], 'INIT_DAMAGE', 1) or 1)
        interval = _zone['rounds'][0]['interval']
    else:
        damage, interval = round_info['damage'], round_info['interval']
    if _zone['elapsed'] < _zone['hurt_at']:
        return False
    _zone['hurt_at'] = _zone['elapsed'] + interval
    zone_hurt(player, damage, DEATH_ZONE)
    return True


def zone_hurt(player, amount, cause=None):
    try:
        old = int(player.hp)
    except Exception:
        return None
    new = max(SELF_MIN_HP, old - int(round(amount)))
    if new == old:
        return new
    player.hp = new
    changed = getattr(player, 'set_hp', None)
    if callable(changed):
        try:
            changed(old)
        except Exception:
            if once('zone-set-hp'):
                log_error('local-battle-zone-hp-error')
    if new <= 0:
        player_died(player, cause)
    return new


# -- the red zone -------------------------------------------------------------

def new_bomb_plan(config):
    params = getattr(config, 'BOMB_PARAM', None)
    if params is None:
        return None
    return {
        'next': float(getattr(params, 'BOMB_FIRST_TIME_DELAY', 90) or 90),
        'warn': float(getattr(params, 'START_BOMB_DELAY', 30) or 30),
        'count': int(getattr(params, 'BOMB_COUNT', 45) or 45),
        'duration': float(getattr(params, 'BOMB_DURATION', 45) or 45),
        'every': float(getattr(params, 'BOMB_PERSIST_TIME', 360) or 360),
        'range': float(getattr(params, 'BOMB_RANGE', 100) or 100),
        'radius': float(getattr(params, 'BOMB_REGION_RADIUS', 2000) or 2000),
        'region': None,
    }


def run_red_zone(state, now=None):
    bomb = _zone.get('bomb')
    if not bomb:
        return False
    elapsed = _zone['elapsed'] if now is None else now
    region = bomb['region']
    if region is None:
        if elapsed >= bomb['next'] and state['blue'][2] >= RED_ZONE_MIN_BLUE:
            start_red_zone(state['blue'], elapsed)
        return False
    if elapsed < region['bombs_at']:
        return False
    if not region['announced']:
        region['announced'] = True
    step = bomb['duration'] / max(1, bomb['count'])
    dropped = 0
    while region['left'] > 0 and elapsed >= region['next_drop'] and dropped < RED_ZONE_DROPS_PER_TICK:
        region['left'] -= 1
        region['next_drop'] += step
        dropped += 1
        drop_bomb(region, bomb['range'])
    if region['left'] > 0 and elapsed >= region['next_drop']:
        region['next_drop'] = elapsed + step        # fell behind (zone skipped ahead): keep the pace
    if region['left'] <= 0:
        end_red_zone()
        bomb['next'] = region['started'] + bomb['every']
    return True


def start_red_zone(blue, elapsed, center=None):
    bomb = _zone['bomb']
    radius = bomb['radius']
    bomb['regions'] = int(bomb.get('regions') or 0) + 1
    if center is None:
        # Its own seed (the round and which bombing this is): the same area
        # in every game window, however their zone ticks fell.
        import random
        randomizer = random.Random('%s-red-%d' % (match_uuid(), bomb['regions']))
        room = max(0.0, blue[2] - radius)
        angle = randomizer.uniform(0.0, 2.0 * math.pi)
        distance = room * math.sqrt(randomizer.random())
        center = (blue[0] + distance * math.cos(angle), blue[1] + distance * math.sin(angle))
    bomb['region'] = {'center': center, 'started': elapsed, 'bombs_at': elapsed + bomb['warn'],
                      'next_drop': elapsed + bomb['warn'], 'left': bomb['count'], 'announced': False,
                      'number': bomb['regions']}
    space = zone_space()
    try:
        space.notifyBombRegion(True, vector2(space, center[0], center[1]), radius)
    except Exception:
        if once('zone-red'):
            log_error('local-battle-red-zone-error')
    log('local-battle-red-zone', center=[round(center[0]), round(center[1])], radius=radius)
    return center


def end_red_zone():
    bomb = _zone.get('bomb') or {}
    region = bomb.get('region')
    if region is None:
        return False
    bomb['region'] = None
    space = zone_space()
    try:
        space.notifyBombRegion(False, vector2(space, region['center'][0], region['center'][1]), 0)
    except Exception:
        pass
    return True


def drop_bomb(region, blast_range):
    import random
    randomizer = random.Random('%s-bomb-%d-%d' % (match_uuid(), int(region.get('number') or 0),
                                                 int(region.get('left') or 0)))
    radius = _zone['bomb']['radius']
    angle = randomizer.uniform(0.0, 2.0 * math.pi)
    distance = radius * math.sqrt(randomizer.random())
    x = region['center'][0] + distance * math.cos(angle)
    z = region['center'][1] + distance * math.sin(angle)
    ground = ground_height(x, z)
    if not ground:
        player = current_player()
        ground = _point(player.position)[1] if player is not None else 0.0
    space = zone_space()
    physics_module = sys.modules.get('libclaudia.Classes.Physics')
    try:
        space.bombInPoint(physics_module.Vector3(x, ground, z), blast_range)
    except Exception:
        if once('zone-bomb'):
            log_error('local-battle-zone-bomb-error')
    return (x, ground, z)


def on_bomb_damage(player, *_args, **_kwargs):
    zone_hurt(player, RED_ZONE_DAMAGE, DEATH_BOMB)
    return None


# -- chat: /zone, /redzone ----------------------------------------------------

def cmd_zone(player, args):
    action = args[0] if args else 'status'
    if action in ('off', 'stop'):
        stop_zone()
        return 'Safe zone stopped.'
    if action in ('on', 'start', 'restart'):
        start_zone()
        return 'Safe zone restarted: the first circle shows in %s.' % clock_text(
            _zone['times'][0][0] / _zone['speed']) if _zone.get('on') else 'This map has no safe zone.'
    if action == 'here':
        position = _point(player.position)
        start_zone(first_center=(position[0], position[2]))
        return 'Safe zone restarted around you.'
    if not _zone.get('on'):
        return 'The safe zone is off. /zone on starts it.'
    if action in ('next', 'skip'):
        state = zone_state(_zone['start'], _zone['circles'], _zone['times'], _zone['rounds'], _zone['elapsed'])
        _zone['elapsed'] += state['rest'] + 0.01
        return 'Skipped ahead.'
    if action == 'speed':
        try:
            _zone['speed'] = max(0.1, min(100.0, float(args[1])))
        except (IndexError, ValueError):
            return 'Usage: /zone speed <x> (1 = normal, 10 = ten times faster)'
        return 'Safe zone runs %gx.' % _zone['speed']
    state = zone_state(_zone['start'], _zone['circles'], _zone['times'], _zone['rounds'], _zone['elapsed'])
    if state['white'] is None:
        return 'First safe zone shows in %s.' % clock_text(state['rest'] / _zone['speed'])
    if state['phase'] == 'done':
        return 'Final safe zone reached.'
    doing = 'closes in' if state['phase'] == 'wait' else 'finishes closing in'
    return 'Zone %d/%d %s %s (radius %d m).' % (state['stage'], len(_zone['rounds']), doing,
                                              clock_text(state['rest'] / _zone['speed']),
                                              int(state['white'][2] / 10.0))


def cmd_red_zone(player, args):
    if not _zone.get('on') or not _zone.get('bomb'):
        return 'The safe zone is off. /zone on starts it.'
    if args and args[0] in ('off', 'stop', 'clear'):
        end_red_zone()
        return 'Red zone cleared.'
    end_red_zone()
    state = zone_state(_zone['start'], _zone['circles'], _zone['times'], _zone['rounds'], _zone['elapsed'])
    center = None
    if args and args[0] == 'here':
        position = _point(player.position)
        center = (position[0], position[2])
    start_red_zone(state['blue'], _zone['elapsed'], center)
    return 'Red zone called in: bombs in %ds.' % int(_zone['bomb']['warn'] / _zone['speed'])


CHAT_COMMANDS.update({'zone': cmd_zone, 'circle': cmd_zone, 'redzone': cmd_red_zone, 'bomb': cmd_red_zone})
CHAT_HELP = CHAT_HELP[:-1] + (
    '/zone [on|off|here|next|speed <x>] - the safe zone',
    '/redzone [here|off] - call in a bombing run',
) + CHAT_HELP[-1:]


# --------------------------------------------------------------------------
# The battle royale flow: the island countdown (the space's own PREPARE stage,
# mapData.PREPARE_TIME), then the plane across the map (PLANE_PARAM), the jump,
# the free fall and the parachute (SKYDIVING_PARAM heights), and the landing -
# where the loot, the cars and the bots are put down around you.
# --------------------------------------------------------------------------

BEFORE_FIGHT_STATUS = 2                 # BattleGroundGameStatusEnum.BEFORE_FIGHT
PLANE_CLASS = 'Plane'
PLANE_MIN_WAIT = 3.0
PLANE_DROP_BELOW = 30.0                 # jumpers start this far under the plane
FALL_PHASE = {'NORMAL': 0, 'BEFORE_FALL': 1, 'CAN_FALL': 2, 'BEFORE_OPEN_PARACHUTE': 3,
              'CAN_OPEN_PARACHUTE': 4, 'PARACHUTE_OPENED': 5}
POSE_STAND = 0
POSE_FALL = 5
POSE_DRIVE = 9                          # const.PlayerPose.DRIVE
DIVE_POLL = 0.2
DIVE_LANDED = 30.0                      # this close above the ground counts as landed
DIVE_TIMEOUT = 240.0
DIVE_PROBE = 20000.0
DIVE_MIN_TIME = 3.0
LANDING_LOOT_RADIUS = 600.0
LANDING_BOT_MIN = 400.0
LANDING_BOT_MAX = 2500.0
_flight = {'stage': 'island', 'token': 0, 'landed_once': False}


def flight_config():
    config = zone_config()
    plane = getattr(config, 'PLANE_PARAM', None) if config is not None else None
    dive = getattr(config, 'SKYDIVING_PARAM', None) if config is not None else None
    return config, plane, dive


def number_list(values, size):
    out = [float(value) for value in list(values or [])[:size]]
    return out + [0.0] * (size - len(out))


def plane_path(center, center_radius, start_radius, randomizer):
    """Start on the START_RADIUS circle, pass within CENTER_RADIUS of the map
    centre, leave on the far side of the circle."""
    cx, cz = center
    angle = randomizer.uniform(0.0, 2.0 * math.pi)
    start = (cx + start_radius * math.cos(angle), cz + start_radius * math.sin(angle))
    spin = randomizer.uniform(0.0, 2.0 * math.pi)
    reach = center_radius * math.sqrt(randomizer.random())
    aim = (cx + reach * math.cos(spin), cz + reach * math.sin(spin))
    dx, dz = aim[0] - start[0], aim[1] - start[1]
    size = math.hypot(dx, dz) or 1.0
    dx, dz = dx / size, dz / size
    length = 2.0 * ((cx - start[0]) * dx + (cz - start[1]) * dz)
    end = (start[0] + dx * length, start[1] + dz * length)
    return start, end


def in_box(box, x, z):
    return len(box) == 4 and box[0] <= x <= box[2] and box[1] <= z <= box[3]


def schedule_plane():
    space = zone_space()
    try:
        start = float(space.gameStageStartTime)
        prepare = float(_field_of(space.mapData, 'PREPARE_TIME') or 0)
        wait = start + prepare - server_now()
    except Exception:
        wait = 0.0
    _flight['token'] += 1
    _flight['stage'] = 'island'
    call_later(max(PLANE_MIN_WAIT, wait), board_plane, _flight['token'])
    log('local-battle-plane-scheduled', wait=round(max(PLANE_MIN_WAIT, wait), 1))
    return wait


def board_plane(token=None, player=None):
    if token is not None and token != _flight.get('token'):
        return False
    if BATTLE.get('phase') != 'fighting':
        return False
    player = player or current_player()
    config, plane, _dive = flight_config()
    if player is None or plane is None:
        log('local-battle-plane-skipped', reason='no plane parameters')
        land_without_plane(player)
        return False
    import random
    randomizer = random.Random(match_uuid() + '-plane-%d' % _flight['token'])
    center = number_list(getattr(plane, 'CENTER_POS', None), 2)
    start, end = plane_path(center, float(getattr(plane, 'CENTER_RADIUS', 0) or 0),
                            float(getattr(plane, 'START_RADIUS', 30000) or 30000), randomizer)
    height = float(getattr(plane, 'HEIGHT', 10000) or 10000)
    yaw = math.atan2(end[0] - start[0], end[1] - start[1])
    plane_id = create_plane(start, height, yaw)
    if plane_id is None:
        land_without_plane(player)
        return False
    _flight.update(stage='plane', plane=plane_id, start=start, end=end, height=height, yaw=yaw,
                   speed=float(getattr(plane, 'SPEED', 727) or 727), box=number_list(getattr(plane, 'JUMP_BOX', None), 4),
                   travelled=0.0, length=math.hypot(end[0] - start[0], end[1] - start[1]),
                   clock=time.time(), can_jump=False, warned=False, aboard=True)
    try:
        player.planeID = plane_id
    except Exception:
        log_error('local-battle-plane-error')
    _flight['routed'] = False
    set_space_field(zone_space(), 'planeEntityIDs', [plane_id], False)
    strip_loadout(player)                       # the island's gun stays on the island
    stop_island_music()
    schedule_airdrops()
    log('local-battle-island-gun-cleared', gun=BATTLE.pop('island_gun', None), state='plane')
    set_space_field(zone_space(), 'gameStatus', BEFORE_FIGHT_STATUS)
    set_player_field(player, 'leftPlayerNumOnPlane', max(1, int(getattr(zone_space(), 'aliveNum', 1) or 1)))
    set_fall_phase(player, FALL_PHASE['BEFORE_FALL'])
    start_zone()
    try:
        player.behaviour.StartCoroutine(plane_frames(_flight['token']))
    except Exception:
        log_error('local-battle-plane-error')
    log('local-battle-plane', start=[round(v) for v in start], end=[round(v) for v in end], height=height)
    return True


def install_plane_guard():
    """Plane.enterWorld seats the player in the plane whose id is
    player.planeID (Avatar.getOnPlane -> self.gameObject.SendMessage).  While
    a map loads the player has no gameObject yet: it raised, the engine called
    enterWorld again every frame (10000+ times) and the load never ended.
    Then the plane enters the world without seating anyone."""
    try:
        module = sys.modules.get(PLANE_CLASS) or __import__(PLANE_CLASS)
        cls = getattr(module, PLANE_CLASS)
    except Exception:
        return False
    if cls.__dict__.get('_rl_plane_guard'):
        return True
    original = cls.__dict__.get('enterWorld')
    if original is None:
        return False

    def enter_world(self, *args):
        try:
            import BigWorld
            player = BigWorld.player()
        except Exception:
            player = None
        bodiless = player is not None and getattr(player, 'gameObject', None) is None
        if bodiless and getattr(player, 'planeID', None) == getattr(self, 'id', None):
            saved = player.planeID
            try:
                player.planeID = 0
                return original(self, *args)
            finally:
                try:
                    player.planeID = saved
                except Exception:
                    pass
        return original(self, *args)

    cls.enterWorld = enter_world
    cls._rl_plane_guard = True
    log('local-battle-plane-guard-installed')
    return True


def create_plane(start, height, yaw):
    try:
        import BigWorld
        space = BATTLE['space'] or getattr(current_player(), 'spaceID', 0)
        made = BigWorld.createEntity(PLANE_CLASS, space, 0, (start[0], height, start[1]), (0.0, 0.0, yaw),
                                     {'mode': _const_value('PlaneWorkMode', 'PEOPLE', {'PEOPLE': 1})})
    except Exception:
        log_error('local-battle-plane-create-error')
        return None
    return getattr(made, 'id', made)


def plane_frames(token):
    while _flight.get('stage') == 'plane' and _flight.get('token') == token:
        yield None
        try:
            fly_plane()
        except Exception:
            if once('plane-frame'):
                log_error('local-battle-plane-frame-error')


def plane_position():
    share = min(1.0, _flight['travelled'] / max(1.0, _flight['length']))
    start, end = _flight['start'], _flight['end']
    return (start[0] + (end[0] - start[0]) * share, _flight['height'], start[1] + (end[1] - start[1]) * share)


def fly_plane(now=None):
    now = time.time() if now is None else now
    _flight['travelled'] += _flight['speed'] * max(0.0, min(0.2, now - _flight['clock']))
    _flight['clock'] = now
    point = plane_position()
    plane = _resolve_entity(_flight['plane'])
    if plane is not None and not isinstance(plane, (int, long_type)):      # not in the world yet: an id
        if type(getattr(plane, 'filter', None)).__name__ != 'DumbFilter':
            client_filter(plane)
        if not _flight.get('routed'):
            _flight['routed'] = set_plane_route(plane)
        _place(plane, point, _flight['yaw'])
    player = current_player()
    inside = in_box(_flight['box'], point[0], point[2])
    if _flight['aboard'] and player is not None:
        if inside and not _flight['can_jump']:
            _flight['can_jump'] = True
            set_fall_phase(player, FALL_PHASE['CAN_FALL'])
        elif _flight['can_jump'] and not inside and not _flight['warned']:
            _flight['warned'] = True
            jump_out(player)
    if _flight['travelled'] >= _flight['length']:
        end_plane(player)
    return point


def route_point(x, y, z):
    vector = getattr(sys.modules.get('Math'), 'Vector3', None)
    if vector is not None:
        try:
            return vector(float(x), float(y), float(z))
        except Exception:
            pass
    return RoutePoint(x, y, z)


class RoutePoint(object):
    def __init__(self, x, y, z):
        self.x, self.y, self.z = float(x), float(y), float(z)


def set_plane_route(plane):
    """The map draws the flight line (UIDtsMap.drawPlaneRoute) from the
    plane's movePath, rotated to the way it flies."""
    start, end, height = _flight['start'], _flight['end'], _flight['height']
    try:
        plane.movePath = [route_point(start[0], height, start[1]), route_point(end[0], height, end[1])]
        return True
    except Exception:
        if once('plane-route'):
            log_error('local-battle-plane-route-error')
        return False


def end_plane(player):
    if _flight.get('aboard') and player is not None:
        jump_out(player)
    _flight['stage'] = 'gone'
    set_space_field(zone_space(), 'planeEntityIDs', [], False)
    set_space_field(zone_space(), 'gameStatus', ZONE_FIGHT_STATUS)
    try:
        import BigWorld
        BigWorld.destroyEntity(_flight['plane'])
    except Exception:
        pass
    return True


def on_get_off_plane(player, *_args, **_kwargs):
    if _flight.get('stage') != 'plane' or not _flight.get('aboard'):
        return None
    if not _flight.get('can_jump'):
        return None
    call_later(WEAPON_SWITCH_DELAY, jump_out, player)
    return None


def jump_out(player):
    if not _flight.get('aboard'):
        return False
    _flight['aboard'] = False
    x, y, z = plane_position()
    old = getattr(player, 'planeID', 0)
    try:
        player.planeID = 0
        player.set_planeID(old)
    except Exception:
        log_error('local-battle-jump-error')
    apply_pose(player, POSE_FALL)
    land_player(player, (x, y - PLANE_DROP_BELOW, z))
    set_fall_phase(player, FALL_PHASE['BEFORE_OPEN_PARACHUTE'])
    bump(player, 'leftPlayerNumOnPlane', -1)
    _flight['dive_started'] = time.time()
    call_later(DIVE_POLL, watch_dive, player, _flight['token'])
    log('local-battle-jump', at=[round(x), round(y), round(z)])
    return True


def set_player_field(player, name, value):
    old = getattr(player, name, None)
    try:
        setattr(player, name, value)
    except Exception:
        return False
    changed = getattr(player, 'set_' + name, None)
    if callable(changed):
        try:
            changed(old)
        except Exception:
            if once('player-field-' + name):
                log_error('local-battle-player-field-error', name=name)
    return True


def set_fall_phase(player, phase):
    if player is None or int(getattr(player, 'fallPhase', 0) or 0) == phase:
        return False
    return set_player_field(player, 'fallPhase', phase)


def on_change_fall_phase(player, phase=0, *_args, **_kwargs):
    try:
        phase = int(phase)
    except Exception:
        return None
    call_later(WEAPON_SWITCH_DELAY, set_fall_phase, player, phase)
    return None


def height_above_ground(player):
    """How far above the ground the player is, or None while the ground
    under them has not streamed in yet (that must not read as "landed")."""
    point = _point(player.position)
    surface = surface_under(point)
    if surface is None:
        ground = ground_height(point[0], point[2])
        if not ground:
            return None
        surface = ground
    return point[1] - surface


def surface_under(point):
    physics_module = sys.modules.get('libclaudia.Classes.Physics')
    ray_module = sys.modules.get('libclaudia.Classes.Ray')
    if physics_module is None or ray_module is None:
        return None
    try:
        hit = ray_module.RaycastHit()
        if physics_module.Physics.RaycastWithScene(physics_module.Vector3(point[0], point[1], point[2]),
                                                   physics_module.Vector3(0.0, -1.0, 0.0), hit, DIVE_PROBE):
            return _point(hit.point)[1]
    except Exception:
        pass
    return None


def watch_dive(player, token):
    if token != _flight.get('token') or BATTLE.get('phase') != 'fighting':
        return False
    _config, _plane, dive = flight_config()
    can_open = float(getattr(dive, 'HEIGHT_CAN_OPEN_PARACHUTE', 5000) or 5000)
    must_open = float(getattr(dive, 'HEIGHT_MUST_OPEN_PARACHUTE', 2000) or 2000)
    phase = int(getattr(player, 'fallPhase', 0) or 0)
    try:
        height = height_above_ground(player)
    except Exception:
        height = None
    timed_out = time.time() - _flight.get('dive_started', time.time()) > DIVE_TIMEOUT
    if height is not None:
        if phase == FALL_PHASE['BEFORE_OPEN_PARACHUTE'] and height <= can_open:
            set_fall_phase(player, FALL_PHASE['CAN_OPEN_PARACHUTE'])
        elif phase in (FALL_PHASE['BEFORE_OPEN_PARACHUTE'], FALL_PHASE['CAN_OPEN_PARACHUTE']) and height <= must_open:
            open_parachute(player)
    on_ground = character_on_ground(player)
    diving = time.time() - _flight.get('dive_started', 0.0)
    back_to_normal = phase == FALL_PHASE['NORMAL'] and diving > DIVE_MIN_TIME
    down = on_ground or (height is not None and height <= DIVE_LANDED)
    if timed_out or back_to_normal or (phase == FALL_PHASE['PARACHUTE_OPENED'] and diving > DIVE_MIN_TIME and down):
        return landed(player)
    call_later(DIVE_POLL, watch_dive, player, token)
    return True


def character_on_ground(player):
    flag = getattr(getattr(move_unit(player), 'character', None), 'onGround', False)
    try:
        return bool(flag() if callable(flag) else flag)
    except Exception:
        return False


def open_parachute(player):
    try:
        player.gameObject.SendMessage('startOpenParachute')
        return True
    except Exception:
        if once('open-parachute'):
            log_error('local-battle-parachute-error')
    set_fall_phase(player, FALL_PHASE['PARACHUTE_OPENED'])
    return False


def landed(player):
    set_fall_phase(player, FALL_PHASE['NORMAL'])
    if int(getattr(player, 'pose', 0) or 0) != POSE_STAND:
        apply_pose(player, POSE_STAND)
    _flight['stage'] = 'landed' if _flight.get('stage') != 'plane' else 'plane'
    if not _flight.get('landed_once'):
        _flight['landed_once'] = True
        try:
            point = _point(player.position)
        except Exception:
            point = None
        if point is not None:
            settle_world(point)
    log('local-battle-landed')
    return True


def land_without_plane(player):
    """No plane on this map: play from where we stand."""
    _flight['stage'] = 'landed'
    if not _flight.get('landed_once') and player is not None:
        _flight['landed_once'] = True
        settle_world(_point(player.position))
    if not _zone.get('on'):
        start_zone()
    return True


def settle_world(point):
    """Loot and cars stream in from the map's own spots (start_world_stream);
    the bots come down around the player."""
    import random
    randomizer = random.Random(match_uuid() + '-landing')
    if not _world.get('on'):
        start_world_stream()
    if not _world.get('loot'):
        scatter_loot(loot_plan((point[0], point[2]), randomizer))
    if not _world.get('cars'):
        place_vehicles_near(point, randomizer)
    place_bots_near(point, randomizer)
    return True


def place_vehicles_near(point, randomizer):
    saved = BATTLE.get('spawn')
    BATTLE['spawn'] = point
    try:
        return place_vehicles(randomizer=randomizer)
    finally:
        BATTLE['spawn'] = saved


def place_bots_near(point, randomizer, count=None):
    count = count if count is not None else int((BATTLE.get('match') or {}).get('bots') or 0)
    births = [spot for spot in _world.get('births') or []
              if LANDING_BOT_MIN <= math.hypot(spot[0] - point[0], spot[2] - point[2]) <= LANDING_BOT_MAX]
    randomizer.shuffle(births)
    points = [[round(value, 2) for value in spot] for spot in births[:count]]
    for _index in range(count - len(points)):
        angle = randomizer.uniform(0.0, 2.0 * math.pi)
        distance = randomizer.uniform(LANDING_BOT_MIN, LANDING_BOT_MAX)
        x, z = point[0] + distance * math.cos(angle), point[2] + distance * math.sin(angle)
        ground = ground_height(x, z)
        points.append([round(x, 2), round(ground if ground else point[1], 2), round(z, 2)])
    if points:
        send(BOT_PREFIX + json.dumps({'action': 'place', 'points': points}))
    return points


def cmd_plane(player, args):
    if args and args[0] in ('jump', 'off'):
        if _flight.get('aboard'):
            jump_out(player)
            return 'Jumped.'
        return 'You are not on the plane.'
    _flight['token'] += 1
    if board_plane(None, player):
        return 'Plane takes off - jump when the button shows.'
    return 'The plane could not start here.'


def cmd_airdrop(player, args):
    """A supply plane drops a box right by you (to try the airdrop out)."""
    if BATTLE.get('phase') != 'fighting' or player is None:
        return 'Only in a match.'
    x, y, z = _point(player.position)
    yaw = float(getattr(player, 'yaw', 0.0) or 0.0)
    x, z = x + AIRDROP_NEAR * math.sin(yaw), z + AIRDROP_NEAR * math.cos(yaw)
    ground = ground_height(x, z) or y
    _airdrops['asked'] = _airdrops.get('asked', 0) + 1
    # A number no other window uses (theirs have their own entity id in it):
    # the same plane, box and contents in every window, and a shared box key.
    index = ASKED_AIRDROP_BASE + int(BATTLE.get('entity_id') or 0) * 100 + _airdrops['asked']
    spot = (x, ground, z, 'asked')
    if drop_supply(_airdrops['token'], index, spot):
        emit('airdrop', {'index': index, 'spot': [x, ground, z]})
        return 'Supply plane incoming - the box lands in front of you.'
    return 'No airdrop here.'


ASKED_AIRDROP_BASE = 100000


AIRDROP_NEAR = 60.0
CHAT_COMMANDS.update({'plane': cmd_plane, 'airdrop': cmd_airdrop})
CHAT_HELP = CHAT_HELP[:-1] + ('/plane - board the plane again (/plane jump to bail out)',
                              '/airdrop - a supply drop right in front of you') + CHAT_HELP[-1:]



# --------------------------------------------------------------------------
# The world from the map's level data (shared.levelConfig): DTSProp (item
# spots in every house and building), DTSCar (vehicle spots on the roads),
# DTSRobotBirthPoint (where bots come in).  Each spot is rolled once per match
# (seeded by the match uuid); loot only exists near the player and is put away
# again far off, cars come in when the player gets near and then stay.
# --------------------------------------------------------------------------

WORLD_POLL = 1.0
LOOT_STREAM_RADIUS = 1500.0
LOOT_DROP_RADIUS = 2500.0
LOOT_CELL = 1000.0
LOOT_SPOT_CHANCE = 0.45
LOOT_RICH_CHANCE = 0.8                  # the map's special spot groups
LOOT_RICH_GROUPS = (3, 9, 191)
LOOT_GUN_CHANCE = 0.22
LOOT_AMMO_CHANCE = 0.15
LOOT_SPAWNS_PER_TICK = 40
CAR_SHARE = 0.35
CAR_STREAM_RADIUS = 2500.0
_world = {'on': False, 'token': 0}


def level_record(map_id=None):
    try:
        import shared.levelConfig as level_config
        return level_config.tables.getLevelData(int(map_id or BATTLE.get('map'))).todict()
    except Exception:
        if once('level-data'):
            log_error('local-battle-level-data-error')
        return None


def level_points(record, section):
    out = []
    for item in list((record or {}).get(section) or []):
        try:
            x, y, z = (float(value) for value in item['point'][:3])
        except Exception:
            continue
        direction = list(item.get('direction') or [0.0, 0.0, 0.0])
        out.append((x, y, z, item.get('group_id'), float(direction[2]) if len(direction) > 2 else 0.0))
    return out


def grid_of(points, cell):
    grid = {}
    for index, point in enumerate(points):
        grid.setdefault((int(math.floor(point[0] / cell)), int(math.floor(point[2] / cell))), []).append(index)
    return grid


def near_indexes(grid, cell, x, z, radius):
    reach = int(math.ceil(radius / cell))
    cx, cz = int(math.floor(x / cell)), int(math.floor(z / cell))
    for gx in range(cx - reach, cx + reach + 1):
        for gz in range(cz - reach, cz + reach + 1):
            for index in grid.get((gx, gz), ()):
                yield index


def roll_spot(seed, index, group):
    """What lies on spot ``index``: [] or [(prop, amount, dx, dz)...]."""
    import random
    randomizer = random.Random('%s-loot-%d' % (seed, index))
    chance = LOOT_RICH_CHANCE if group in LOOT_RICH_GROUPS else LOOT_SPOT_CHANCE
    if randomizer.random() >= chance:
        return []
    pick = randomizer.random()
    if pick < LOOT_GUN_CHANCE:
        gun = randomizer.choice(LOOT_GUNS)
        bullet = gun_bullet(gun)
        items = [(gun, 1, 0.0, 0.0)]
        if bullet:
            items.append((bullet, LOOT_AMMO_STACK, LOOT_AMMO_OFFSET * 10.0, 0.0))
        return items
    if pick < LOOT_GUN_CHANCE + LOOT_AMMO_CHANCE:
        bullet = gun_bullet(randomizer.choice(LOOT_GUNS))
        return [(bullet, LOOT_AMMO_STACK, 0.0, 0.0)] if bullet else []
    prop, amount = randomizer.choice(LOOT_SINGLES)
    return [(prop, amount, 0.0, 0.0)]


def start_world_stream():
    record = level_record()
    spots = level_points(record, 'DTSProp')
    roads = level_points(record, 'DTSCar')
    births = level_points(record, 'DTSRobotBirthPoint')
    if not spots and not roads:
        return False
    import random
    randomizer = random.Random(match_uuid() + '-cars')
    chosen = [spot for spot in roads if randomizer.random() < CAR_SHARE]
    _world['token'] += 1
    _world.update(on=True, seed=match_uuid(), spots=spots, grid=grid_of(spots, LOOT_CELL), live={}, gone=set(),
                  cars=chosen, car_grid=grid_of(chosen, LOOT_CELL), cars_made=set(),
                  births=[(spot[0], spot[1], spot[2]) for spot in births], loot=bool(spots))
    call_later(WORLD_POLL, world_tick, _world['token'])
    log('local-battle-world', spots=len(spots), cars=len(chosen), births=len(births))
    return True


def world_tick(token):
    if not _world.get('on') or _world.get('token') != token:
        return False
    if BATTLE.get('phase') != 'fighting':
        _world['on'] = False
        return False
    player = current_player()
    try:
        if player is not None:
            track_movement(player)
        if player is not None and not getattr(player, 'planeID', 0):
            point = _point(player.position)
            stream_loot(point)
            stream_cars(point)
            stream_boats(point)
    except Exception:
        if once('world-tick'):
            log_error('local-battle-world-error')
    call_later(WORLD_POLL, world_tick, token)
    return True


def stream_loot(point):
    x, _y, z = point
    live, gone, spots = _world['live'], _world['gone'], _world['spots']
    for index, made in list(live.items()):
        if any(_loot.get(entity_id, {}).get('amount') != amount for entity_id, amount in made):
            gone.add(index)                     # picked from: it stays as it is now
            del live[index]
            continue
        spot = spots[index]
        if math.hypot(spot[0] - x, spot[2] - z) > LOOT_DROP_RADIUS:
            for entity_id, _amount in made:
                remove_loot(entity_id)
            del live[index]
    spawned = 0
    for index in near_indexes(_world['grid'], LOOT_CELL, x, z, LOOT_STREAM_RADIUS):
        if spawned >= LOOT_SPAWNS_PER_TICK:
            break
        if index in live or index in gone:
            continue
        spot = spots[index]
        if math.hypot(spot[0] - x, spot[2] - z) > LOOT_STREAM_RADIUS:
            continue
        items = roll_spot(_world['seed'], index, spot[3])
        if not items:
            gone.add(index)
            continue
        made = []
        for slot, (prop, amount, dx, dz) in enumerate(items):
            key = 's%d:%d' % (index, slot)
            left = int(amount) - int(_shared['taken'].get(key, 0))
            if left <= 0:
                continue                        # taken in another window
            entity_id = spawn_loot(prop, left, spot[0] + dx, spot[2] + dz, spot[1])
            if entity_id is not None:
                _loot[entity_id].update(key=key, full=int(amount))
                made.append((entity_id, left))
        live[index] = made
        spawned += 1
    return spawned


BOAT = ('LandBoat', 25011, 130005)
BOAT_SHARE = 0.35                       # of the road spots near water, how many get a boat
BOAT_REACH = (600.0, 1000.0, 1500.0)    # how far from the road a boat may lie
BOAT_DIRECTIONS = 8
BOAT_PROBE_UP = 800.0
BOAT_PROBE_DOWN = 3000.0
BOAT_MIN_DEPTH = 5.0


def surface_material(x, z, top):
    """(height, material kind) of what is first hit straight down at (x, z);
    None when nothing there has collision yet (not streamed in)."""
    physics_module = sys.modules.get('libclaudia.Classes.Physics')
    ray_module = sys.modules.get('libclaudia.Classes.Ray')
    if physics_module is None or ray_module is None:
        return None
    try:
        hit = ray_module.RaycastHit()
        if not physics_module.Physics.RaycastWithScene(physics_module.Vector3(x, top + BOAT_PROBE_UP, z),
                                                       physics_module.Vector3(0.0, -1.0, 0.0), hit,
                                                       BOAT_PROBE_UP + BOAT_PROBE_DOWN):
            return None
        return _point(hit.point)[1], str(getattr(hit, 'material_kind', '') or '')
    except Exception:
        return None


def boat_spot(index, spot):
    """Water near road spot ``index``: its own seeded directions and
    distances, the same in every window.  (x, water, z, yaw), False when it
    has none, None while the ground there is not loaded yet."""
    import random
    randomizer = random.Random('%s-boat-%d' % (match_uuid(), index))
    if randomizer.random() >= BOAT_SHARE:
        return False
    turn = randomizer.uniform(0.0, 2.0 * math.pi)
    yaw = randomizer.uniform(-math.pi, math.pi)
    loaded = False
    for reach in BOAT_REACH:
        for step in range(BOAT_DIRECTIONS):
            angle = turn + step * 2.0 * math.pi / BOAT_DIRECTIONS
            x, z = spot[0] + reach * math.cos(angle), spot[2] + reach * math.sin(angle)
            found = surface_material(x, z, spot[1])
            if found is None:
                continue
            loaded = True
            height, material = found
            if material != 'water':
                continue
            ground = ground_height(x, z)
            if ground and height - ground < BOAT_MIN_DEPTH:
                continue                        # the shallows: it would sit on the sand
            return (x, height, z, yaw)
    return False if loaded else None


def stream_boats(point):
    x, _y, z = point
    tried = _world.setdefault('boats_tried', set())
    made = 0
    for index in near_indexes(_world['car_grid'], LOOT_CELL, x, z, CAR_STREAM_RADIUS):
        if index in tried:
            continue
        spot = _world['cars'][index]
        if math.hypot(spot[0] - x, spot[2] - z) > CAR_STREAM_RADIUS:
            continue
        found = boat_spot(index, spot)
        if found is None:
            continue                            # not loaded: tried again later
        tried.add(index)
        if not found:
            continue
        class_name, land, tps = BOAT
        boat_id = spawn_vehicle(class_name, land, tps, found[0], found[2], found[1] - VEHICLE_LIFT, found[3])
        if boat_id is not None:
            share_car(boat_id, 'w%d' % index)
            made += 1
            log('local-battle-boat', spot=index, position=[round(found[0]), round(found[1]), round(found[2])])
    return made


def stream_cars(point):
    x, _y, z = point
    made = _world['cars_made']
    for index in near_indexes(_world['car_grid'], LOOT_CELL, x, z, CAR_STREAM_RADIUS):
        if index in made:
            continue
        spot = _world['cars'][index]
        if math.hypot(spot[0] - x, spot[2] - z) > CAR_STREAM_RADIUS:
            continue
        made.add(index)
        class_name, land, tps = VEHICLE_FLEET[index % len(VEHICLE_FLEET)]
        car_id = spawn_vehicle(class_name, land, tps, spot[0], spot[2], spot[1], spot[4])
        if car_id is not None:
            share_car(car_id, 'c%d' % index)
    return len(made)


# --------------------------------------------------------------------------
# The end of the round for the player: death (or the last one standing) and
# the game's own result screen - iBattleGround.onBattleGroundResult(gameType,
# teamSize, rank, total, bannerID, results, killerInfo) -> UIBattlegroundsResult
# ("#2/10", solo, ranked, kills...).
# --------------------------------------------------------------------------

RESULT_DELAY = 2.5
RESULT_GAME_TYPE = 4                    # GameEnterType.RANKED
RESULT_TEAM_SIZE = 1                    # solo


def result_team_size():
    """The size the match was played at (the START ticket: the party's)."""
    try:
        return max(1, int((BATTLE.get('ticket') or {}).get('teamSize') or RESULT_TEAM_SIZE))
    except Exception:
        return RESULT_TEAM_SIZE
DEATH_ZONE = 'zone'
DEATH_BOMB = 'bomb'
DEATH_SELF = 'self'
DEATH_PLAYER = 'player'
DEATH_FEED = {DEATH_ZONE: 'I_DTS_I_POISONED_KILL', DEATH_BOMB: 'I_DTS_I_BOMB_KILL'}
GP_PER_KILL = 10
GP_PER_RANK = 15
GP_SECONDS_PER_POINT = 30
GP_UNITS_PER_POINT = 2000.0
RESULT_BASE_EXP = 20
RESULT_EXP_PER_KILL = 5
_round = {'over': False}


def match_total():
    """Everyone who was in the round: us, the bots and the other players
    (the most the LEFT count ever showed)."""
    return max(1 + int((BATTLE.get('match') or {}).get('bots') or 0), int(_round.get('field') or 0))


BANNER_WIN = 7                          # const.BattleGroundBannerType.WIN_SINGLE: "Winner winner chicken dinner"
BANNER_TOP10 = 9                        # LOSE_SINGLE_TOP10
BANNER_LOSE = 10                        # LOSE


def result_banner(rank):
    """The banner the server picked for the result screen (bannerID): the
    win banner and its music for the last one standing."""
    if rank <= 1:
        return BANNER_WIN
    return BANNER_TOP10 if rank <= 10 else BANNER_LOSE


def player_died(player, cause=None, point=None, killer=None):
    if _round.get('over'):
        return False
    _round['over'] = True
    if cause != DEATH_PLAYER:
        _pvp['died'] = {'cause': str(cause or ''), 'killer': 0, 'weapon': ''}
    space = zone_space()
    rank = max(1, int(getattr(space, 'aliveNum', 1) or 1))
    try:
        position = point or _point(player.position)
    except Exception:
        position = (0.0, 0.0, 0.0)
    try:
        player.deadInGame = True
    except Exception:
        pass
    try:
        player.onDie(position, 0, weapon_record(0, 0, HIT_EXPLODE), CHEST_PART, HIT_EXPLODE)
    except Exception:
        if once('player-die'):
            log_error('local-battle-player-die-error')
    feed = DEATH_FEED.get(cause)
    texts = sys.modules.get('errtxt')
    if feed and texts is not None and getattr(texts, feed, None):
        tip_text(str(getattr(texts, feed)).replace('#cD6D6D6', '').replace('#n', ''))
    if space is not None:
        bump(space, 'aliveNum', -1, floor=1)
    call_later(BODY_LINGER, hide_my_body, player)
    try:
        leave_my_heritage(player)               # where we fell (position may be the killer's)
    except Exception:
        log_error('local-battle-my-heritage-error')
    stop_zone()
    _world['on'] = False
    log('local-battle-player-died', cause=cause, rank=rank)
    call_later(RESULT_DELAY, show_result, player, rank)
    return True


def hide_my_body(player):
    """Our body once it has fallen: gone, our death box is where it lay (the
    camera is on the killer by then - our body stood on in the view)."""
    if BATTLE.get('phase') not in ('fighting', 'over'):
        return False
    try:
        player.setVisible(False)
        return True
    except Exception:
        if once('hide-my-body'):
            log_error('local-battle-hide-body-error')
        return False


def result_record(player, rank, total):
    """One row of UIBattlegroundsResult.showResult: results[gid]."""
    kills = int(getattr(player, 'battleKillNum', 0) or 0)
    survived = max(0, int(time.time() - float(BATTLE.get('step_started') or time.time())))
    moved = _round.get('moved', 0.0)
    rank_gp = max(0, total - rank + 1) * GP_PER_RANK
    kill_gp = kills * GP_PER_KILL
    time_gp = survived // GP_SECONDS_PER_POINT
    move_gp = int(moved / GP_UNITS_PER_POINT)
    exp = match_exp(rank, total, kills, survived)
    return {
        'gid': int(getattr(player, 'gid', 0) or 0),
        'name': avatar_name(player),
        'nickname': avatar_name(player),
        'kill': kills,
        'score': kills * 100 + (total - rank) * 10,
        'flag': '', 'nationalFlag': '', 'nameplate': 0, 'dtsNameplateAppearance': 0,
        'moveDis': round(moved / 10000.0, 1),
        'collectCount': int(_round.get('collected', 0)),
        'healTeammate': 0,
        'surviveTime': survived,
        'gps': (time_gp, kill_gp, rank_gp, 0, move_gp, 0),
        'dailyFirstGameReward': (0, 0),
        'randomGP': 0,
        'randomScore': 0,
        'shuffle_bonus': 0,
        'anniversaryScoreProtect': 0,
        'add': 0,
        'cycle': 0,
        'GPMul': 1,
        'exp': exp,
        'newBraveBookPayState': 0,
    }


EXP_PER_HOUR = 500                      # LevelSystemParam EXP_PER_HOUR_IN_2_HOUR
WIN_EXP = 50


def match_exp(rank, total, kills, survived):
    """Experience for one match: time played, placement, kills, a win."""
    return int(RESULT_BASE_EXP + survived * EXP_PER_HOUR / 3600 + max(0, total - rank)
               + kills * RESULT_EXP_PER_KILL + (WIN_EXP if rank == 1 else 0))


def match_summary(record, rank, total):
    """What the profile's STATS page keeps from this match."""
    hits = int(_round.get('hits', 0))
    return {'rank': int(rank), 'total': int(total), 'teamSize': result_team_size(), 'ranked': True,
            'kills': int(record.get('kill', 0)), 'damage': int(_round.get('damage', 0)),
            'hits': hits, 'fired': max(hits, int(_round.get('fired', 0))),
            'headshots': int(_round.get('headshots', 0)), 'surviveTime': int(record.get('surviveTime', 0)),
            'moveDis': float(record.get('moveDis', 0.0)), 'collectCount': int(record.get('collectCount', 0)),
            'maxKillDis': int(_round.get('max_kill_dis', 0.0) / 10.0), 'exp': int(record.get('exp', 0)),
            'weapons': dict((gun, dict(counts)) for gun, counts in (_round.get('weapons') or {}).items()),
            # the backend's Activity tasks (features/activity.py): a match counts
            # once (the round's uuid, the same from show_result and
            # settle_unfinished_match), maps-restricted tasks read the map
            'match_id': match_uuid(), 'map': int(BATTLE.get('map') or 0),
            'vehicle': bool(_round.get('vehicle')),
            # the Special Distinction's pick-up / use missions
            'pickups': dict(_round.get('pickups') or {}), 'uses': dict(_round.get('uses') or {})}


def record_match(summary):
    recorder = getattr(LOBBY, 'record_match', None)
    if not callable(recorder):
        return None
    try:
        return recorder(summary)
    except Exception:
        log_error('local-battle-record-error')
        return None


# --------------------------------------------------------------------------
# Supply airdrops: the map's own AIR_DROP configuration (battleground params,
# map 700 -> 799: ACTIVATE_TIME 120 s after take-off, INTERVAL 150 s,
# RANDOM_TIMES 6-7 drops, DROP_SPEED), the level's airdrop points
# (shared.levelConfig DTSAirDrop) inside the safe circle, and contents from
# the game's airdrop table (shared.tables.randomDtsAirDrop).  The box is the
# game's falling airdrop entity, opened like a death box.
# --------------------------------------------------------------------------

AIRDROP_CLASS = 'DtsAvatarHeroAirDrop'
AIRDROP_MODEL = 'character/female_battlegrounds/supplybox/supplybox_ros.gim'
AIRDROP_FALL_SECONDS = 20.0
AIRDROP_TICK = 0.05
AIRDROP_SAFE_SHARE = 0.8                # inside this share of the safe circle's radius
AIRDROP_EXTRAS = 4
_airdrops = {'token': 0, 'falling': {}}


def airdrop_config():
    params = battleground_params(BATTLE.get('map'))
    config = _field_of(params, 'AIR_DROP') if params is not None else None
    if config is None:
        return None
    times = list(_field_of(config, 'RANDOM_TIMES') or [6, 7]) + [6, 7]
    return {'activate': float(_field_of(config, 'ACTIVATE_TIME') or 120),
            'interval': float(_field_of(config, 'INTERVAL') or 150),
            'times': (int(times[0]), int(times[1])),
            'specific': [float(value) for value in list(_field_of(config, 'SPECIFIC_INTERVAL') or [])],
            'speed': float(_field_of(config, 'DROP_SPEED') or 50),
            'group': int(_field_of(config, 'DROP_GROUP_ID') or 0)}


def schedule_airdrops():
    """Take-off starts the airdrop clock (the fight's start online)."""
    config = airdrop_config()
    if config is None:
        log('local-battle-airdrops', scheduled=0, reason='no AIR_DROP for the map')
        return 0
    import random
    _airdrops['token'] += 1
    token = _airdrops['token']
    randomizer = random.Random(match_uuid() + '-airdrop')
    count = randomizer.randint(min(config['times']), max(config['times']))
    delays = []
    for index in range(count):
        gap = config['specific'][index] if index < len(config['specific']) else config['interval']
        delays.append(config['activate'] if index == 0 else delays[-1] + gap)
    for index, delay in enumerate(delays):
        call_later(delay, drop_supply, token, index)
    log('local-battle-airdrops', scheduled=count, at=[round(delay) for delay in delays])
    return count


def safe_circle():
    """(x, z, radius) of the safe (white) circle now, else the first one."""
    shown = (_zone.get('shown') or {}).get('white')
    if shown is not None:
        return shown
    circles = _zone.get('circles') or []
    return circles[0] if circles else None


def level_airdrop_points(map_id, group):
    """The level's own airdrop points (LevelData DTSAirDrop, by group)."""
    try:
        import shared.levelConfig as level_config
        found = level_config.levelData.getDtsAirDropsPositions(int(map_id)) or {}
    except Exception:
        return []
    entries = found.get(group) or found.get(str(group)) or []
    if not entries:
        entries = [entry for values in found.values() for entry in values]
    points = []
    for entry in entries:
        point = _position_in(entry)
        if point is not None:
            points.append(point)
    return points


ISLAND_MARGIN = 500.0
_islands = {}


def island_area(map_id):
    """(x, z, radius) around the Prepare Island's spawn points: no supply
    box comes down there (nobody is left on it once the plane has gone)."""
    if map_id in _islands:
        return _islands[map_id]
    points = level_points(level_record(map_id), 'RebornPosition') if map_id else []
    area = None
    if points:
        cx = sum(point[0] for point in points) / len(points)
        cz = sum(point[2] for point in points) / len(points)
        reach = max(math.hypot(point[0] - cx, point[2] - cz) for point in points)
        area = (cx, cz, reach + ISLAND_MARGIN)
    _islands[map_id] = area
    return area


def on_island(area, point):
    return area is not None and math.hypot(point[0] - area[0], point[2] - area[1]) <= area[2]


def airdrop_spot(randomizer, config):
    circle = safe_circle()
    inside = []
    if circle is not None:
        cx, cz, radius = circle[0], circle[1], circle[2] * AIRDROP_SAFE_SHARE
        inside = [point for point in level_airdrop_points(BATTLE.get('map'), config['group'])
                  if math.hypot(point[0] - cx, point[2] - cz) <= radius]
        if inside:
            point = randomizer.choice(inside)
            return point[0], point[1], point[2], 'level'
        # No fixed points on this map: anywhere in the safe circle, on one of
        # the level's own item spots (real ground, known height even where
        # the landscape has not streamed in).
        island = island_area(BATTLE.get('map'))
        spots = [spot for spot in (_world.get('spots') or [])
                 if math.hypot(spot[0] - cx, spot[2] - cz) <= radius and not on_island(island, spot)]
        if spots:
            spot = randomizer.choice(spots)
            return spot[0], spot[1], spot[2], 'circle'
        angle = randomizer.uniform(0.0, 2.0 * math.pi)
        reach = radius * math.sqrt(randomizer.random())
        return cx + reach * math.cos(angle), None, cz + reach * math.sin(angle), 'circle'
    x, _y, z = _point(current_player().position)
    angle = randomizer.uniform(0.0, 2.0 * math.pi)
    return x + 300.0 * math.cos(angle), None, z + 300.0 * math.sin(angle), 'near'


def airdrop_items(randomizer):
    """The game's airdrop table roll, else a death box's worth plus extras."""
    items = []
    try:
        import shared.tables as tables
        if not getattr(tables, 'dtsAirDropTable', None):
            tables.preprocessDtsAirDrop()       # the server builds it; the client never ran it
        # The table rolls with the global random: seeded from this drop's own
        # randomizer for the roll, the same box in every game window.
        import random as global_random
        state = global_random.getstate()
        try:
            global_random.seed(randomizer.random())
            props = tables.randomDtsAirDrop(int(BATTLE.get('map') or 0))
        finally:
            global_random.setstate(state)
        for entry in props or []:
            values = list(entry) if isinstance(entry, (list, tuple)) else [entry, 1]
            items.append((int(values[0]), int(values[1]) if len(values) > 1 else 1))
    except Exception:
        items = []
    source = 'table'
    if not items:
        source = 'loot'
        items = [tuple(entry[:2]) for entry in heritage_items(randomizer).values()]
        for _index in range(AIRDROP_EXTRAS):
            items.append(randomizer.choice(LOOT_SINGLES))
    return dict(('airdrop-%d' % index, [prop, amount, {}]) for index, (prop, amount) in enumerate(items)), source


AIRDROP_PLANE_LEAD = 8000.0              # the supply plane comes in from this far before the drop point
AIRDROP_PLANE_SPEED = 727.0             # the transport plane's PLANE_PARAM SPEED
AIRDROP_LIGHT_REFRESH = (0.5, 1.5, 3.0, 6.0)


def drop_supply(token, index, spot=None):
    """A supply plane (Plane in PlaneWorkMode.PROP: the airdrop plane and its
    engine sound, heard near it) flies over the drop point and lets the box
    go there."""
    if token != _airdrops.get('token') or BATTLE.get('phase') != 'fighting':
        return False
    config = airdrop_config() or {'speed': 50.0, 'group': 0}
    import random
    randomizer = random.Random('%s-airdrop-%d' % (match_uuid(), index))
    x, ground, z, where = spot or airdrop_spot(randomizer, config)
    items, source = airdrop_items(randomizer)
    if ground is None:
        ground = ground_height(x, z) or _point(current_player().position)[1]
    drop = {'index': index, 'x': x, 'z': z, 'ground': ground, 'where': where, 'items': items, 'source': source,
            'speed': config['speed'], 'top': ground + config['speed'] * AIRDROP_FALL_SECONDS}
    angle = randomizer.uniform(0.0, 2.0 * math.pi)
    dx, dz = math.sin(angle), math.cos(angle)
    start = (x - dx * AIRDROP_PLANE_LEAD, z - dz * AIRDROP_PLANE_LEAD)
    height = drop['top'] + PLANE_DROP_BELOW
    plane_id = None
    try:
        import BigWorld
        space = BATTLE['space'] or getattr(current_player(), 'spaceID', 0)
        made = BigWorld.createEntity(PLANE_CLASS, space, 0, (start[0], height, start[1]), (0.0, 0.0, angle),
                                     {'mode': _const_value('PlaneWorkMode', 'PROP', {'PROP': 2})})
        plane_id = getattr(made, 'id', made)
    except Exception:
        log_error('local-battle-airdrop-plane-error', index=index)
    if plane_id is None:
        return release_supply(token, drop)          # no plane: the box still comes
    _airdrops.setdefault('planes', {})[plane_id] = dict(
        drop=drop, start=start, yaw=angle, direction=(dx, dz), height=height, travelled=0.0,
        length=2.0 * AIRDROP_PLANE_LEAD, clock=time.time(), dropped=False)
    run_airdrops(token)
    tip_text('Supply drop incoming!')
    log('local-battle-airdrop-plane', index=index, plane=plane_id, start=[round(v) for v in start],
        drop=[round(x), round(z)], height=round(height))
    return True


def run_airdrops(token):
    """Supply planes and falling boxes move every frame (a coroutine, like
    the transport plane's): moved on a timer they stepped visibly."""
    if _airdrops.get('driver') == token:
        return True
    _airdrops['driver'] = token
    try:
        current_player().behaviour.StartCoroutine(airdrop_frames(token))
        return True
    except Exception:
        if once('airdrop-coroutine'):
            log_error('local-battle-airdrop-coroutine-error')
    call_later(AIRDROP_TICK, airdrop_tick, token)
    return False


def airdrops_moving():
    return bool(_airdrops.get('planes')) or bool(_airdrops.get('falling'))


def airdrop_step(token):
    try:
        fly_airdrop_planes(token, again=False)
        fall_airdrops(token, again=False)
    except Exception:
        if once('airdrop-step'):
            log_error('local-battle-airdrop-step-error')


def airdrop_frames(token):
    while _airdrops.get('token') == token and airdrops_moving():
        yield None
        airdrop_step(token)
    if _airdrops.get('driver') == token:
        _airdrops['driver'] = None


def airdrop_tick(token):
    """The timer fallback when no coroutine can run."""
    airdrop_step(token)
    if _airdrops.get('token') == token and airdrops_moving():
        call_later(AIRDROP_TICK, airdrop_tick, token)
    elif _airdrops.get('driver') == token:
        _airdrops['driver'] = None


def fly_airdrop_planes(token, again=True):
    if token != _airdrops.get('token'):
        return False
    now = time.time()
    planes = _airdrops.get('planes') or {}
    for plane_id, flight in list(planes.items()):
        flight['travelled'] += AIRDROP_PLANE_SPEED * max(0.0, min(0.2, now - flight['clock']))
        flight['clock'] = now
        share = flight['travelled']
        point = (flight['start'][0] + flight['direction'][0] * share, flight['height'],
                 flight['start'][1] + flight['direction'][1] * share)
        plane = _resolve_entity(plane_id)
        if plane is not None and not isinstance(plane, (int, long_type)):
            try:
                hold_entity(plane, point, flight['yaw'])
            except Exception:
                if once('airdrop-plane-frame'):
                    log_error('local-battle-airdrop-plane-frame-error')
        if not flight['dropped'] and share >= AIRDROP_PLANE_LEAD:
            flight['dropped'] = True
            release_supply(token, flight['drop'])
        if share >= flight['length']:
            planes.pop(plane_id, None)
            try:
                import BigWorld
                BigWorld.destroyEntity(plane_id)
            except Exception:
                pass
    if planes and again:
        run_airdrops(token)
    return True


def release_supply(token, drop):
    if token != _airdrops.get('token') or BATTLE.get('phase') != 'fighting':
        return False
    x, z, ground, top, items = drop['x'], drop['z'], drop['ground'], drop['top'], drop['items']
    install_heritage_cell()
    box_class = sys.modules.get(AIRDROP_CLASS) and getattr(sys.modules[AIRDROP_CLASS], AIRDROP_CLASS, None)
    if box_class is None:
        try:
            box_class = getattr(__import__(AIRDROP_CLASS), AIRDROP_CLASS)
        except Exception:
            box_class = None
    if box_class is not None:
        box_class.AIR_DROP_MODEL = AIRDROP_MODEL
        box_class.DROP_DOWN_TIME = int(AIRDROP_FALL_SECONDS)
        install_airdrop_leave(box_class)
    try:
        import BigWorld
        space = BATTLE['space'] or getattr(current_player(), 'spaceID', 0)
        # drop: the supply crate (AIR_DROP_MODEL, onLoadAirDrop) - without it
        # DtsPlayerHeritage took the box for a death box (mizang).
        made = BigWorld.createEntity(AIRDROP_CLASS, space, 0, (x, top, z), (0.0, 0.0, 0.0),
                                     {'name': 'Airdrop', 'items': items, 'dropping': True, 'drop': 1,
                                      'heritageMode': _const_value('HeritageMode', 'NORMAL_DROP',
                                                                   {'NORMAL_DROP': 1})})
    except Exception:
        log_error('local-battle-airdrop-error', index=drop['index'])
        return False
    entity_id = getattr(made, 'id', made)
    _heritages[entity_id] = items
    share_box(entity_id, 'a%d' % int(drop['index']), items)    # /airdrop ones too: relayed, numbered apart
    _airdrops['falling'][entity_id] = {'x': x, 'y': top, 'z': z, 'ground': ground, 'speed': drop['speed'],
                                       'clock': time.time(), 'born': time.time()}
    run_airdrops(token)
    for delay in AIRDROP_LIGHT_REFRESH:
        call_later(delay, place_airdrop_light, entity_id, x, ground, z)
    log('local-battle-airdrop', index=drop['index'], box=entity_id, where=drop['where'], source=drop['source'],
        position=[round(x), round(top), round(z)], items=[entry[0] for entry in items.values()])
    return True


def hold_entity(entity, position, yaw=None):
    entity = _resolve_entity(entity)
    if entity is None or isinstance(entity, (int, long_type)):
        return False
    try:
        import BigWorld
        if type(getattr(entity, 'filter', None)).__name__ != 'ClientFilter':
            entity.filter = BigWorld.ClientFilter()
    except Exception:
        if once('entity-filter'):
            log_error('local-battle-entity-filter-error')
    return _place(entity, position, yaw)


AIRDROP_MISSING_WAIT = 5.0


def hold_box(box, position):
    """Move a supply box so it stays moved: with the filter it is made with
    (and the AvatarFilter its model sets on load) the box went back to where
    it was created - up in the sky - as soon as nobody moved it; a
    ClientFilter keeps the position the client gives it."""
    try:
        import BigWorld
        if type(getattr(box, 'filter', None)).__name__ != 'ClientFilter':
            box.filter = BigWorld.ClientFilter()
    except Exception:
        if once('box-filter'):
            log_error('local-battle-box-filter-error')
    return _place(box, position)


def place_airdrop_light(entity_id, x, ground, z):
    """The beam of light over the landing spot (DtsAvatarHeroAirDrop's
    airDropLightObj, and its landing area) stands where the game's
    Physics.DropToGround found the ground under the box - nothing, far from
    you, where no collision is loaded yet.  It goes where the box lands."""
    box = vehicle_entity(entity_id)
    module = sys.modules.get(AIRDROP_CLASS)
    if box is None or module is None:
        return False
    if not _airdrops['falling'].get(entity_id):
        hold_box(box, (x, ground + HERITAGE_LIFT, z))       # landed: keep it there
    try:
        position = module.Vector3(float(x), float(ground), float(z))
        box.ground_pos = position
        for name in ('lightObj', 'col_obj'):
            obj = getattr(box, name, None)
            if obj is not None:
                obj.transform.position = position
    except Exception:
        if once('airdrop-light'):
            log_error('local-battle-airdrop-light-error')
        return False
    return True


def install_airdrop_leave(box_class):
    """DtsAvatarHeroAirDrop.leaveWorld removes its landing-area collider with
    ``self.colliderContainer`` - which the box model's own collider replaced
    when it loaded - and DtsPlayerHeritage.leaveWorld then removes the model
    with it again: Physics.RemoveGameObject raised "list.remove(x): x not in
    list" on every try, the box never left the world and the next map load
    hung at 52%.  Each collider now goes with its own container, and nothing
    in the clean-up can stop the rest of it."""
    if box_class.__dict__.get('_rl_safe_leave'):
        return False
    enter = box_class.__dict__.get('enterWorld')
    module = sys.modules.get(box_class.__module__)
    if enter is None or module is None:
        return False

    def enter_world(self, *args):
        result = enter(self, *args)
        try:
            self._rl_area_container = self.colliderContainer     # the landing area's, until the model loads
        except Exception:
            self._rl_area_container = None
        return result

    def leave_world(self, *args):
        area = getattr(self, '_rl_area_container', None)
        steps = (lambda: module.Physics.RemoveGameObject(self.col_obj, area) if area is not None else None,
                 lambda: module.Object.Destroy(self.col_obj),
                 lambda: module.Object.Destroy(self.lightObj) if hasattr(self, 'lightObj') else None,
                 lambda: module.Timer.delTimer(self.timerLandDetect) if getattr(self, 'timerLandDetect', 0) else None)
        for step in steps:
            try:
                step()
            except Exception:
                pass
        try:
            if getattr(self, 'colliderContainer', None) is area:
                del self.colliderContainer          # no model collider of its own to remove
        except Exception:
            pass
        try:
            super(box_class, self).leaveWorld(*args)
        except Exception:
            if once('airdrop-leave'):
                log_error('local-battle-airdrop-leave-error')

    box_class.enterWorld = enter_world
    box_class.leaveWorld = leave_world
    box_class._rl_safe_leave = True
    log('local-battle-airdrop-leave-installed')
    return True


def fall_airdrops(token, again=True):
    """The box comes down at DROP_SPEED and stops on the ground."""
    if token != _airdrops.get('token'):
        return False
    now = time.time()
    for entity_id, state in list(_airdrops['falling'].items()):
        box = vehicle_entity(entity_id)
        if box is None:
            # Made this frame, in the world from the next: wait for it, the
            # fall starting then (only a box gone for good is let go).
            state['clock'] = now
            if now - state.get('born', now) > AIRDROP_MISSING_WAIT:
                _airdrops['falling'].pop(entity_id, None)
            continue
        ground = ground_height(state['x'], state['z']) or state['ground']
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
                place_airdrop_light(entity_id, state['x'], state['ground'], state['z'])
                log('local-battle-airdrop-landed', box=entity_id, position=[round(state['x']), round(state['y']), round(state['z'])])
        except Exception:
            if once('airdrop-fall'):
                log_error('local-battle-airdrop-fall-error')
    if _airdrops['falling'] and again:
        run_airdrops(token)
    return True


def settle_unfinished_match(player):
    """Leaving before the result screen: the match still counts (as ending
    at your place now) - its EXP, stats and rank change are saved, not lost
    with the battle."""
    if _round.get('shown') or _round.get('settled') or not BATTLE.get('match') or player is None:
        return False
    _round['settled'] = True
    space = zone_space()
    rank = max(1, int(getattr(space, 'aliveNum', 1) or 1))
    total = max(rank, match_total())
    try:
        record = result_record(player, rank, total)
        owner = owner_result(rank, total, record)
        record['score'] = owner['score']
        record_match(match_summary(record, rank, total))
    except Exception:
        log_error('local-battle-settle-error')
        return False
    log('local-battle-settled-on-leave', rank=rank, total=total, kills=record.get('kill'), exp=record.get('exp'))
    return True


def show_result(player, rank):
    if _round.get('shown'):
        return False
    _round['shown'] = True
    _round['over'] = True
    total = max(rank, match_total())
    record = result_record(player, rank, total)
    owner = owner_result(rank, total, record)
    record['score'] = owner['score']
    _round['rank_change'] = owner['score']
    record_match(match_summary(record, rank, total))
    label_ranked()
    try:
        player.onBattleGroundRankedResult(RESULT_GAME_TYPE, result_team_size(), rank, total, result_banner(rank),
                                          {record['gid']: record}, owner,
                                          {'killerID': int(_pvp.get('killer_body') or 0)})
    except Exception:
        log_error('local-battle-result-error', rank=rank)
        tip_text('#%d/%d' % (rank, total))
        return False
    log('local-battle-result', rank=rank, total=total, kills=record['kill'])
    # The result screen waits for the player: its Exit button (requestLeaveDynamicSpace)
    # goes to the lobby, the rank page is its own button.  It no longer moves on by itself.
    return True


RESULT_PAGE_SECONDS = 8.0
RANK_PAGE_SECONDS = 4.0
RANK_POINTS_PER_SECOND = 30.0
RANK_STAR_SECONDS = 2.0
RANK_STAR_POINTS = 100


def rank_page_seconds():
    """The rank page counts the change one point per frame and pauses on
    every star it fills: stay until it has finished."""
    change = abs(int(_round.get('rank_change') or 0))
    stars = change // RANK_STAR_POINTS + 1
    return RANK_PAGE_SECONDS + change / RANK_POINTS_PER_SECOND + stars * RANK_STAR_SECONDS


def result_screen():
    try:
        import Globals
        return getattr(Globals.uiMgr, RESULT_SCREEN, None)
    except Exception:
        return None


def result_rank_page():
    """The result screen moves on by itself: rank page, then the lobby."""
    if BATTLE.get('phase') == 'idle':
        return False
    screen = result_screen()
    shown = False
    if screen is not None and callable(getattr(screen, 'showDanPanel', None)):
        try:
            screen.showDanPanel()
            shown = True
        except Exception:
            if once('rank-page'):
                log_error('local-battle-rank-page-error')
    call_later(rank_page_seconds() if shown else 0.1, result_to_lobby)
    return shown


def result_to_lobby():
    if BATTLE.get('phase') == 'idle':
        return False
    return leave_battle(current_player())


RANK_WIN_POINTS = 70
RANK_KILL_POINTS = 8
RANK_PLACE_POINTS = 5
RANK_ENTRY_COST = 10
RANKED_LABEL = 'Ranked'


def rank_points(rank, total, kills):
    """Solo ranked score change: a win is worth about one Bronze tier (100);
    placement and kills add to it, an early death costs a little."""
    bonus = RANK_WIN_POINTS if rank == 1 else 0
    return bonus + (total - rank) * RANK_PLACE_POINTS + kills * RANK_KILL_POINTS - RANK_ENTRY_COST


RANK_SCAN_LIMIT = 5000


def tier_of(score):
    value = rank_dict(score)
    return (value.get('section'), value.get('subSection'))


def next_tier_start(score, step):
    """The first score past ``score`` (step +1 or -1) that is in another tier."""
    tier = tier_of(score)
    probe = score
    for _index in range(RANK_SCAN_LIMIT):
        probe += step
        if probe < 0:
            return None
        if tier_of(probe) != tier:
            return probe
    return None


def one_tier_at_most(before, after):
    """The rank page animates one tier change; a bigger jump made it loop.
    A match moves you at most into the next tier up (or down)."""
    if after > before:
        first = next_tier_start(before, 1)
        if first is None:
            return after
        second = next_tier_start(first, 1)
        return min(after, second - 1) if second is not None else after
    if after < before:
        first = next_tier_start(before, -1)
        if first is None:
            return after
        second = next_tier_start(first, -1)
        return max(after, second + 1) if second is not None else after
    return after


def stored_rank_score():
    function = getattr(LOBBY, 'rank_score', None)
    try:
        return int(function()) if callable(function) else 0
    except Exception:
        return 0


def rank_dict(score):
    module = sys.modules.get('rank_utils')
    if module is None:
        try:
            module = __import__('rank_utils')
        except Exception:
            module = None
    try:
        return dict(module.getRankDict(int(score)))
    except Exception:
        return {'section': 0, 'subSection': 0, 'score': int(score)}


def owner_result(rank, total, record):
    """The ranked score card (the "Next" page): the lobby's score before and after."""
    before = stored_rank_score()
    after = one_tier_at_most(before, max(0, before + rank_points(rank, total, record['kill'])))
    old, new = rank_dict(before), rank_dict(after)
    save_rank_score(after)
    return {'oldVal': old, 'newVal': new, 'credit': 0, 'round_credit': 0, 'dan': new.get('section', 1),
            'useBraveBookForScore': False, 'score': after - before}


def save_rank_score(score):
    saver = getattr(LOBBY, 'save_state_durable', None) or getattr(LOBBY, 'save_state', None)
    if not callable(saver):
        return False
    try:
        ok, _reason = saver(lobby={'rankScore': int(score)})
        return ok
    except Exception:
        log_error('local-battle-rank-save-error')
        return False


def label_ranked():
    return translate_mode_names()


def strip_loadout(player):
    """The island's guns and pickups stay on the island."""
    for slot in GUN_SLOTS + (PISTOL_SLOT,):
        if not gun_slot_free(player, slot):
            remove_gun(player, slot)
    if int(getattr(player, 'dtsWeapon%d' % BOMB_SLOT, 0) or 0):
        empty_bomb_slot(player)
    melee = getattr(player, 'dtsWeapon%d' % MELEE_SLOT, UNARMED)
    if melee and melee != UNARMED:
        try:
            setattr(player, 'dtsWeapon%d' % MELEE_SLOT, UNARMED)
            player.onWearDtsWeapon(MELEE_SLOT)
        except Exception:
            if once('strip-melee'):
                log_error('local-battle-strip-error', what='melee')
    try:
        items = list(player.dtsItemPackage.itemList.keys())
    except Exception:
        items = []
    for item in items:
        try:
            count = int(player.getDtsItemCnt(item) or 0)
            if count > 0:
                player.onDelDtsFoldedItem(item, count)
        except Exception:
            if once('strip-item'):
                log_error('local-battle-strip-error', what='item', item=item)
    for field in GEAR_FIELDS.values():
        take_off_gear(player, field)
    take_off_backpack(player)
    log('local-battle-loadout-cleared', items=len(items))
    return True


def take_off_gear(player, field):
    try:
        record = getattr(player, field)
        if not int(record['itemID'] or 0):
            return False
        old = dict((key, record[key]) for key in record.keys())
        record['itemID'] = 0
        record['durability'] = 0
    except Exception:
        return False
    look = GEAR_LOOKS[field]
    old_look = getattr(player, look, 0)
    try:
        setattr(player, look, 0)
    except Exception:
        pass
    for callback, args in (('set_' + field, (old,)), ('onWearDtsSafetyGear', (field,)), ('set_' + look, (old_look,))):
        function = getattr(player, callback, None)
        if callable(function):
            try:
                function(*args)
            except Exception:
                if once('ungear-' + callback):
                    log_error('local-battle-gear-callback-error', callback=callback)
    return True


def take_off_backpack(player):
    try:
        previous = int(player.dtsPackage or 0)
    except Exception:
        return False
    if not previous:
        return False
    player.dtsPackage = 0
    try:
        player.dtsItemPackage._packageCapacity = BACKPACK_CAPACITY[0]
    except Exception:
        pass
    for callback, args in (('set_dtsPackage', (previous,)), ('onWearDtsPackage', ())):
        function = getattr(player, callback, None)
        if callable(function):
            try:
                function(*args)
            except Exception:
                pass
    return True


def track_movement(player):
    """Distance walked/driven for the result screen."""
    try:
        point = _point(player.position)
    except Exception:
        return 0.0
    last = _round.get('last_point')
    if last is not None and not getattr(player, 'planeID', 0):
        step = math.hypot(point[0] - last[0], point[2] - last[2])
        if step < 2000.0:
            _round['moved'] = _round.get('moved', 0.0) + step
    _round['last_point'] = point
    return _round.get('moved', 0.0)


# --------------------------------------------------------------------------
# Back to the lobby: the result screen's Exit/Next and the menu's leave send
# base.requestLeaveDynamicSpace; /lobby does the same.  The round is taken
# down here, then the client's own ConnectMonitor.backToLogin loads the login
# level, and the local login brings the lobby back.
# --------------------------------------------------------------------------

LEAVE_DELAY = 0.3
RESULT_SCREEN = 'UIBattlegroundsResult'


def on_leave_battle(player, *_args, **_kwargs):
    if BATTLE.get('phase') not in ('entering', 'fighting', 'over'):
        return None
    call_later(LEAVE_DELAY, leave_battle, player)
    return None


def leave_battle(player=None):
    player = player or current_player()
    if BATTLE.get('phase') == 'fighting':
        settle_unfinished_match(player)
    _airdrops['token'] += 1
    _airdrops['falling'].clear()
    for plane_id in list(_airdrops.get('planes', {})):
        try:
            import BigWorld
            BigWorld.destroyEntity(plane_id)     # still flying: gone with the battle, not into the next
        except Exception:
            pass
    _airdrops.get('planes', {}).clear()
    _airdrops['driver'] = None
    stop_zone()
    _world['on'] = False
    _flight['token'] += 1
    _flight['stage'] = 'island'
    if _noclip.get('on'):
        _noclip['on'] = False
    _round.clear()
    _round.update(over=False, moved=0.0)
    for entity_id in list(_vehicles):
        try:
            import BigWorld
            BigWorld.destroyEntity(entity_id)
        except Exception:
            pass
    _vehicles.clear()
    try:
        import Globals
        Globals.uiMgr.leave_ui(RESULT_SCREEN)
    except Exception:
        pass
    showing = getattr(LOBBY, 'show_return_loading', None)
    if callable(showing):
        showing()
    silence_back_to_login()
    BATTLE['quiet_until'] = time.time() + LEAVE_QUIET_SECONDS
    stop_battle_audio()
    close_battle_screens()
    cancel(player)
    drop_battle_world()
    log('local-battle-left')
    call_later(LEAVE_DELAY, back_to_login)
    returning = getattr(LOBBY, 'return_to_lobby', None)
    if callable(returning):
        call_later(LEAVE_DELAY * 2, returning)
    return True


def drop_battle_world():
    """The battle body is a client entity: no disconnect takes it away.  Drop
    it (and everything else) the way the hall was dropped on the way in, or it
    stays BigWorld.player() and the lobby is never handed over."""
    try:
        import BigWorld
    except Exception:
        return False
    dropped = []
    for name in ('logOff', 'clearAllEntities'):
        function = getattr(BigWorld, name, None)
        if not callable(function):
            continue
        try:
            function()
            dropped.append(name)
        except Exception as error:
            log('local-battle-drop-error', call=name, error='%s: %s' % (type(error).__name__, error))
    try:
        import Globals
        if getattr(Globals.spaceEntity, '_rl_local_space', False) or BATTLE.get('space_entity') is not None:
            Globals.spaceEntity = None
    except Exception:
        pass
    forget_battle_globals()
    BATTLE['space_entity'] = None
    log('local-battle-world-dropped', calls=dropped,
        player=type(current_player()).__name__ if current_player() is not None else None)
    return bool(dropped)


BATTLE_GLOBALS = ('player',)
BATTLE_SCREENS = ('UIBattlegroundsInGame', 'UIBloodScreen', 'UISceneRoot', 'UICompass', 'UIBattleGroundsScope',
                  'UIDtsInFightChat', 'UIDtsCommanderDialogue', 'UIPlayMusic', 'UI3DKilledEffectPanel',
                  'UIJumpTip', 'UIBattlegroundsResult', 'UIBattlegroundsFall', 'UIDtsMap', 'UIDtsPickUp2',
                  'UIDtsPickUp2Heritage', 'UIDtsPopupDispatcher', 'UISelectHero', 'UIBattlegroundsUav',
                  'UIBattlegroundsInGameActionAndEmoji', 'GoldTextJump', 'UISwallow', 'UIDtsPackage2',
                  'UISettingForPC', 'UIDialog', 'UIDeathKillerDisplay', 'UIKillerOverview')
MAP_AMBIENCE_PREFIX = 'tps/amb_'
BATTLE_SOUND_PREFIXES = ('tps/amb_', 'music/')
MUSIC_PREFIXES = ('music/', 'tps_new/tps_g89_music/')


def playing_clips():
    clips = []
    try:
        import gc
        for value in gc.get_objects():
            if type(value).__name__ != 'AudioClip':
                continue
            try:
                if value.isPlaying():
                    clips.append(value)
            except Exception:
                continue
    except Exception:
        pass
    return clips


def remember_lobby_music():
    """What the lobby is playing when START is pressed: put back afterwards."""
    paths = sorted(set(str(getattr(clip, 'path', '') or '') for clip in playing_clips()
                       if str(getattr(clip, 'path', '') or '').startswith(MUSIC_PREFIXES)))
    BATTLE['lobby_music'] = paths
    log('local-battle-lobby-music', paths=paths)
    return paths


def restore_lobby_music():
    """The lobby's music is the game's one BGM player (Globals.audioSource,
    music/new_dataosha/zhujiemian_v1); the battle stopped it and nothing in a
    client-side return plays it again."""
    try:
        import Globals
        source = Globals.audioSource
    except Exception:
        return []
    player = current_player()
    try:
        wanted = bool(player.needBGM()) if callable(getattr(player, 'needBGM', None)) else True
    except Exception:
        wanted = True
    try:
        if source is None or not wanted or source.isPlaying():
            return []
        source.Play()
    except Exception:
        log_error('local-battle-lobby-music-error')
        return []
    log('local-battle-lobby-music-restored')
    return ['bgm']


def stop_battle_audio():
    """The map's ambience (SceneSystem.ChangeWeatherMode: audioEventClip) only
    stops in SceneSystem.OnDestroy, which a client-side battle never reaches."""
    stopped = []
    try:
        import Globals
        space = getattr(Globals, 'spaceEntity', None)
        if callable(getattr(type(space), 'tryStopMusic', None)):
            space.tryStopMusic()
            stopped.append('jukebox')
    except Exception:
        pass
    player = current_player()
    if callable(getattr(type(player), 'clearBattleClip', None)):
        try:
            player.clearBattleClip()
            stopped.append('battle-clips')
        except Exception:
            pass
    keep = set(BATTLE.get('lobby_music') or [])
    scene_system = _scene_system()
    clip = getattr(scene_system, 'audioEventClip', None) if scene_system is not None else None
    if clip is not None:
        try:
            clip.Stop()
            scene_system.audioEventClip = None
            stopped.append('scene')
        except Exception:
            pass
    try:
        import gc
        for value in gc.get_objects():
            if type(value).__name__ != 'AudioClip':
                continue
            try:
                path = str(getattr(value, 'path', '') or '')
                if path.startswith(BATTLE_SOUND_PREFIXES) and path not in keep and value.isPlaying():
                    value.Stop()
                    stopped.append(path)
            except Exception:
                continue
    except Exception:
        pass
    log('local-battle-audio-stopped', stopped=stopped)
    return stopped


def close_battle_screens():
    try:
        import Globals
        ui_mgr = Globals.uiMgr
    except Exception:
        return []
    closed = []
    for name in BATTLE_SCREENS:
        try:
            ui_mgr.destroy_ui_obj(name)
            closed.append(name)
        except Exception:
            continue
    return closed


def forget_battle_globals():
    """Globals.player is the battle body's GameObject; once it is gone the
    next map load (SceneSystem.beforeLoadMap) asks it for its controller and
    fails.  In the hall it is unset, the way it was before the first battle."""
    try:
        import Globals
    except Exception:
        return []
    cleared = []
    for name in BATTLE_GLOBALS:
        if getattr(Globals, name, None) is not None:
            try:
                setattr(Globals, name, None)
                cleared.append(name)
            except Exception:
                pass
    return cleared


def back_to_login():
    BATTLE['own_back_to_login'] = True
    try:
        from helpers.ConnectMonitor import ConnectMonitor
        ConnectMonitor.getInstance().backToLogin()
        return True
    except Exception:
        log_error('local-battle-back-to-login-error')
        return False
    finally:
        BATTLE['own_back_to_login'] = False


def cmd_lobby(player, args):
    call_later(LEAVE_DELAY, leave_battle, player)
    return 'Leaving the battle...'


CHAT_COMMANDS.update({'lobby': cmd_lobby, 'leave': cmd_lobby})
CHAT_HELP = CHAT_HELP[:-1] + ('/lobby - leave the battle and go back to the lobby',) + CHAT_HELP[-1:]
