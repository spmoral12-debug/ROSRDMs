# ==========================================================
# ROS REDEMPTION - SERVER HOT PATCH (MASTER ENGINE)
# ==========================================================
# 1. 40 Bots Random Spawning Across Ghillie Island (476 DTS Birth Points)
# 2. Localized Patrol Walking (_walk uses entity.home wander, NEVER clumps)
# 3. Preserves scattered bot positions on player join (set_spawn)
# 4. Safe join without no_token exception
# 5. Instant 1-player match start (queue_up)
# ==========================================================
import time
import math
import random
import json
import os
from backend_server import battle

# ----------------------------------------------------------
# 1. Load Main Map Coordinates (DTSRobotBirthPoint & RebornPosition)
# ----------------------------------------------------------
MAIN_ISLAND_POINTS = []
REBORN_POINTS = []

try:
    for base_dir in [
        r'C:\DieHardROS\runtime\app\local_update\logs',
        r'C:\DieHardROS\local_update\logs',
        r'C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app\local_update\logs'
    ]:
        p = os.path.join(base_dir, 'level_700.json')
        if os.path.exists(p):
            with open(p, 'r') as f:
                data = json.load(f)
            pts_dict = data.get('points', {})
            
            # 476 Birth points all across Ghillie Island (cities, hills, radar, airbase)
            for pt in pts_dict.get('DTSRobotBirthPoint', []):
                if len(pt) >= 3:
                    MAIN_ISLAND_POINTS.append((float(pt[0]), float(pt[1]), float(pt[2])))
            
            # Spawn Island reborn points
            for pt in pts_dict.get('RebornPosition', []):
                if len(pt) >= 3:
                    REBORN_POINTS.append((float(pt[0]), float(pt[1]), float(pt[2])))
            
            print('[server] ROS Redemption: Loaded %d island birth points & %d reborn points from %s' % (
                len(MAIN_ISLAND_POINTS), len(REBORN_POINTS), p), flush=True)
            break
except Exception as e:
    print('[server] Failed to load level_700 points:', e, flush=True)

# Fallback coordinates if file read fails
if not MAIN_ISLAND_POINTS:
    MAIN_ISLAND_POINTS = REBORN_POINTS or [(0.0, 100.0, 0.0)]

# ----------------------------------------------------------
# 2. Monkey-patch Battle._spawn_bots (40 Distributed Bots with HOME)
# ----------------------------------------------------------
try:
    def redemption_spawn_bots(self):
        bots_count = getattr(self.config, 'bots', 40)
        points_pool = list(MAIN_ISLAND_POINTS)
        if points_pool:
            self._random.shuffle(points_pool)
        
        for index in range(bots_count):
            entity_id = self._new_id()
            if points_pool:
                base_pt = points_pool[index % len(points_pool)]
                jitter_x = self._random.uniform(-15.0, 15.0)
                jitter_z = self._random.uniform(-15.0, 15.0)
                pos = (base_pt[0] + jitter_x, base_pt[1], base_pt[2] + jitter_z)
            else:
                pos = self._spawn_point(getattr(self.config, 'bot_radius', 120.0))
            
            yaw = self._random.uniform(-math.pi, math.pi)
            bot_entity = battle.Entity(
                id=entity_id,
                kind=battle.BOT,
                name='Bot%02d' % (index + 1),
                gid=900000 + entity_id,
                team=index + 2,
                position=pos,
                yaw=yaw
            )
            # CRITICAL: set home and target so bots wander LOCALLY in their assigned area!
            bot_entity.home = pos
            bot_entity.target = pos
            self.entities[entity_id] = bot_entity
            
        print('[server] ROS Redemption: %d bots spawned and distributed across Ghillie Island!' % bots_count, flush=True)

    battle.Battle._spawn_bots = redemption_spawn_bots
except Exception as e:
    print('[server] Error patching _spawn_bots:', e, flush=True)

# ----------------------------------------------------------
# 3. Monkey-patch Battle._walk (Local Wander, Zero Clumping)
# ----------------------------------------------------------
try:
    def redemption_walk(self, entity, step):
        # Guarantee home is always anchored to entity's spawn location
        if entity.home is None:
            entity.home = entity.position

        # If entity arrived at target, pick a new point near its own home
        if entity.target is None or battle._distance(entity.position, entity.target) <= step:
            wander_radius = getattr(battle, 'HOME_WANDER', 40.0)
            entity.target = self._point_near(entity.home, wander_radius)

        x, y, z = entity.position
        tx, _ty, tz = entity.target
        dx, dz = tx - x, tz - z
        length = math.hypot(dx, dz)
        if length < 1e-06:
            return None
        
        new_x = x + (dx / length) * step
        new_z = z + (dz / length) * step
        entity.position = (new_x, y, new_z)
        entity.yaw = math.atan2(dx, dz)

    battle.Battle._walk = redemption_walk
    print('[server] ROS Redemption: Localized bot patrol walk installed (no clumping)!', flush=True)
except Exception as e:
    print('[server] Error patching _walk:', e, flush=True)

# ----------------------------------------------------------
# 4. Monkey-patch Battle.set_spawn (Preserve Scattered Bots)
# ----------------------------------------------------------
try:
    def redemption_set_spawn(self, point, refine=False):
        with self._lock:
            if self.spawn_from != 'config' and not refine:
                return False
            new_spawn = battle._vector(point, self.spawn)
            if new_spawn == self.spawn:
                return False
            self.spawn = new_spawn
            self.spawn_from = 'client'
            # Bots stay distributed at their birth points across Ghillie Island.
            return True

    battle.Battle.set_spawn = redemption_set_spawn
except Exception as e:
    print('[server] Error patching set_spawn:', e, flush=True)

# ----------------------------------------------------------
# 5. Monkey-patch Battle.join (Prevent no_token error)
# ----------------------------------------------------------
try:
    orig_join = getattr(battle.Battle, '_orig_join', None)
    if not orig_join:
        orig_join = battle.Battle.join
        battle.Battle._orig_join = orig_join

    def redemption_join(self, token='', name='Player', gid=0, team=1, look=None):
        token = str(token) if token else 'session_player'
        return orig_join(self, token, name, gid, team, look)

    battle.Battle.join = redemption_join
except Exception as e:
    print('[server] Error patching join:', e, flush=True)

# ----------------------------------------------------------
# 6. Monkey-patch Battle.queue_up (Instant 1-player Match Start)
# ----------------------------------------------------------
try:
    def redemption_queue_up(self, token):
        with self._lock:
            now = self._clock()
            token = str(token) if token else 'player_solo'
            for queued, seen in list(self.queue.items()):
                if now - seen > 15.0:
                    self.queue.pop(queued, None)
            self.queue[token] = now
            need = 1
            if self.go_at is None:
                self.go_at = now
                self.stage_start = time.time() + getattr(battle, 'STAGE_GRACE', 3.0)
            return {
                'ok': True,
                'queued': max(1, len(self.queue)),
                'need': need,
                'go': True,
                'stage_start': round(self.stage_start, 3)
            }

    battle.Battle.queue_up = redemption_queue_up
    print('[server] ROS Redemption battle matchmaker & random bot patches loaded!', flush=True)
except Exception as e:
    print('[server] Error patching queue_up:', e, flush=True)

# ----------------------------------------------------------
# 7. Monkey-patch Battle.place_bots (Never Clump Bots on Client Place)
# ----------------------------------------------------------
try:
    def redemption_place_bots(self, points):
        with self._lock:
            bots = [e for e in self.entities.values() if e.kind == battle.BOT and e.alive]
            pool = list(MAIN_ISLAND_POINTS)
            if pool:
                self._random.shuffle(pool)
            for index, entity in enumerate(bots):
                if pool:
                    base = pool[index % len(pool)]
                    spot = (base[0] + self._random.uniform(-10, 10), base[1], base[2] + self._random.uniform(-10, 10))
                else:
                    spot = entity.position
                entity.position = spot
                entity.home = spot
                entity.target = None
            print('[server] ROS Redemption: %d bots placed dispersed across Ghillie Island!' % len(bots), flush=True)
            return len(bots)

    battle.Battle.place_bots = redemption_place_bots
    print('[server] ROS Redemption: place_bots anti-clump patch installed!', flush=True)
except Exception as e:
    print('[server] Error patching place_bots:', e, flush=True)

# ----------------------------------------------------------
# 8. Starter Equipment Auto-Grant for All Players (Summer Bicycle + Tango)
# ----------------------------------------------------------
try:
    from backend_server import database
    orig_load_char = getattr(database.Database, '_orig_load_char', None)
    if not orig_load_char:
        orig_load_char = database.Database.load_character_data
        database.Database._orig_load_char = orig_load_char

    def redemption_load_character_data(self, conn, gid):
        wallet, data = orig_load_char(self, conn, gid)
        if isinstance(data, dict):
            depot = data.setdefault('depot', {})
            depot.setdefault('140073', {'count': 1, 'expires': 0})
            depot.setdefault('909042', {'count': 1, 'expires': 0})
            eq = data.setdefault('equipped', {})
            eq['dtsBattlegroundPropAppearanceList'] = [x for x in eq.get('dtsBattlegroundPropAppearanceList', []) if x != 140073]
            if not eq.get('dtsInGameActionAppearanceIDs'):
                eq['dtsInGameActionAppearanceIDs'] = [909042, 909030, 909031]
            if not eq.get('dtsInGameActionSuitAppearanceIDs'):
                eq['dtsInGameActionSuitAppearanceIDs'] = [909042]
        return wallet, data

    database.Database.load_character_data = redemption_load_character_data
    print('[server] ROS Redemption: Starter items auto-grant hook installed for all players!', flush=True)
except Exception as e:
    print('[server] Note on load_character_data patch:', e, flush=True)

# ----------------------------------------------------------
# 9. MailServer Robust Detail & Award Hook (Fix KeyError: 0)
# ----------------------------------------------------------
try:
    from backend_server import chat
    import json

    def _redemption_norm_mail_props(props):
        norm = []
        if isinstance(props, str):
            try:
                props = json.loads(props)
                if isinstance(props, str):
                    props = json.loads(props)
            except Exception:
                props = []
        for p in (props or []):
            if isinstance(p, dict):
                gp = p.get('gp') or p.get('gold')
                dia = p.get('payYuanbao') or p.get('freeYuanbao') or p.get('diamonds')
                if gp and int(gp) > 0:
                    norm.append([200001, int(gp)])
                if dia and int(dia) > 0:
                    norm.append([201001, int(dia)])
                item = p.get('item') or p.get('item_id') or p.get('prop_id')
                if item and int(item) > 0:
                    norm.append([int(item), int(p.get('count', 1))])
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                norm.append([int(p[0]), int(p[1])])
        return norm

    def redemption_mail_detail(self, args):
        mail_id = chat._int(args[0], -1) if args else -1
        row = self.db.mail_row(self.account.gid, mail_id)
        if not row:
            return [{'method': 'onLoadMailDetailFailed', 'args': [mail_id]}]
        self.db.read_mail(self.account.gid, mail_id)
        props = _redemption_norm_mail_props(row['props'])
        extra = {'props': props, 'gid': int(row['sender_gid'])}
        return [{'method': 'onLoadMailDetail', 'args': [mail_id, row['content'], extra]}]

    def redemption_mail_award(self, args):
        mail_id = chat._int(args[0], -1) if args else -1
        with self.db.transaction() as conn:
            raw_props = self.db.take_mail_props_in(conn, self.account.gid, mail_id)
        props = _redemption_norm_mail_props(raw_props)
        if not props:
            return {'ok': False, 'callbacks': [], 'tip': 'Nothing to take from this mail.'}

        taken = []
        with self.account.edit() as data:
            for prop in props:
                item = prop[0]
                count = prop[1]
                days = prop[2] if len(prop) > 2 else 0
                if item in chat.MAIL_CURRENCY_PROPS:
                    self.account.grant(data, chat.MAIL_CURRENCY_PROPS[item], count, 'mail:%s' % mail_id)
                else:
                    self.account.add_item(data, item, count, days)
                taken.append([item, count])

        print('[server] ROS Redemption: Awarded mail %s to player: %r' % (mail_id, taken), flush=True)
        return [
            {'method': 'onGetAwardFromMail', 'args': [taken]},
            self.update()
        ]

    chat.MailServer.detail = redemption_mail_detail
    chat.MailServer.award = redemption_mail_award
    print('[server] ROS Redemption: MailServer robust detail & award patch active!', flush=True)
except Exception as e:
    print('[server] Error patching MailServer:', e, flush=True)

# ----------------------------------------------------------
# 10. Profile & Identity RPC Handlers (Rename & Country Flag Change)
# ----------------------------------------------------------
try:
    from backend_server import pyserver
    from backend_server import database
    import re
    import time
    import json
    import os

    FLAG_CODE_REGEX = re.compile(r"^[A-Za-z]{2}$")

    def _sync_local_identity(name):
        try:
            curr_dir = os.path.dirname(os.path.abspath(__file__))
            bases = [
                r'C:\Users\seanj\Documents\ROSRDMs',
                r'C:\DieHardROS',
                os.path.abspath(os.path.join(curr_dir, '..', '..'))
            ]
            for base in bases:
                for rel in [
                    os.path.join('local_update', 'local_identity.json'),
                    os.path.join('runtime', 'app', 'local_update', 'local_identity.json'),
                    os.path.join('ROS_Redemption_Server_Package', 'local_update', 'local_identity.json')
                ]:
                    target = os.path.join(base, rel)
                    if os.path.exists(target):
                        try:
                            with open(target, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                            data['username'] = name
                            with open(target, 'w', encoding='utf-8') as f:
                                json.dump(data, f, indent=2)
                        except Exception:
                            pass
        except Exception:
            pass

    def redemption_change_nickname(server, args, kwargs):
        account = server.account
        try:
            raw_name = args[0] if args else None
            if not raw_name:
                return {'handled': True, 'ok': False, 'tip': 'Please enter a valid nickname.'}
            name = str(raw_name).strip()
            if len(name) > 16:
                return {'handled': True, 'ok': False, 'tip': 'Nickname must be up to 16 characters.'}
            if any(not char.isprintable() for char in name):
                return {'handled': True, 'ok': False, 'tip': 'Nickname contains invalid characters.'}
            
            with account.db.transaction() as conn:
                row = conn.execute(
                    "SELECT nickname, server_id, lobby FROM characters WHERE gid = ?", (account.gid,)
                ).fetchone()
                if row is None:
                    return {'handled': True, 'ok': False, 'tip': 'Character not found.'}
                
                lobby = json.loads(row["lobby"] or "{}")
                if name == row["nickname"]:
                    return {'handled': True, 'ok': False, 'tip': 'Please choose a different name.'}
                
                # Check duplicate name on same server
                taken = conn.execute(
                    "SELECT 1 FROM characters WHERE server_id = ? AND gid <> ? "
                    "AND created = 1 AND nickname = ? COLLATE NOCASE",
                    (row["server_id"], account.gid, name),
                ).fetchone()
                if taken:
                    return {'handled': True, 'ok': False, 'tip': 'That nickname is already taken.'}
                
                # Charge diamonds only if they have enough, but never block
                if lobby.get("freeNickNameUsed"):
                    try:
                        with account.edit_in(conn) as data:
                            account.charge(data, "diamond", 300, "nickname_change")
                    except Exception:
                        pass
                lobby["freeNickNameUsed"] = True
                
                account.db.update_character_in(conn, account.gid, nickname=name, lobby=lobby)
                print(f"[server] ROS Redemption: Nickname changed for GID {account.gid} ({row['nickname']} -> {name})", flush=True)

            _sync_local_identity(name)

            return {
                'handled': True,
                'ok': True,
                'callbacks': [
                    {'method': 'rlRedemptionNickname', 'args': [name]},
                    {'method': 'onChangeNickname', 'args': [0, 'Name changed.']}
                ],
                'props': {
                    'nickname': name,
                    'baseNickname': name,
                    'playerName': name
                },
                'tip': 'Nickname changed successfully!'
            }
        except Exception as e:
            print(f"[server] Error in changeNicknameWithCard: {e}", flush=True)
            return {'handled': True, 'ok': False, 'tip': f'Failed to change name: {e}'}

    def redemption_set_national_flag(server, args, kwargs):
        raw_flag = args[0] if args else None
        if not raw_flag or not isinstance(raw_flag, str) or not FLAG_CODE_REGEX.match(raw_flag):
            return {'handled': True, 'ok': False, 'tip': 'Please select a valid 2-letter country flag.'}
        
        flag = raw_flag.upper()
        account = server.account
        try:
            now = int(time.time())
            with account.db.transaction() as conn:
                row = conn.execute(
                    "SELECT lobby FROM characters WHERE gid = ?", (account.gid,)
                ).fetchone()
                if row is None:
                    return {'handled': True, 'ok': False, 'tip': 'Character not found.'}
                
                lobby = json.loads(row["lobby"] or "{}")
                previous_time = int(lobby.get("nationalFlagSetTime") or 0)
                
                if previous_time:
                    price = 500 if (now - previous_time < 7 * 86400) else 50
                    try:
                        with account.edit_in(conn) as data:
                            account.charge(data, "diamond", price, "flag_change")
                    except Exception:
                        pass
                
                lobby.update(
                    nationalFlag=flag,
                    country=flag,
                    flag=flag,
                    nation=flag,
                    nationalFlagSetTime=now
                )
                account.db.update_character_in(conn, account.gid, lobby=lobby)
                print(f"[server] ROS Redemption: Country flag changed for GID {account.gid} -> {flag}", flush=True)

            return {
                'handled': True,
                'ok': True,
                'callbacks': [
                    {'method': 'rlRedemptionFlag', 'args': [flag, now]},
                    {'method': 'rlOwnFlag', 'args': [flag]},
                    {'method': 'updateNationalityInfo', 'args': [[{'flag': flag, 'setTime': now}]]}
                ],
                'props': {
                    'nationalFlag': flag
                },
                'tip': 'Country flag changed successfully!'
            }
        except Exception as e:
            print(f"[server] Error in setNationalFlag: {e}", flush=True)
            return {'handled': True, 'ok': False, 'tip': f'Failed to change flag: {e}'}

    def redemption_update_lbs(server, args, kwargs):
        return {'handled': True, 'ok': True, 'callbacks': []}

    pyserver.HANDLERS['changeNicknameWithCard'] = redemption_change_nickname
    pyserver.HANDLERS['setNationalFlag'] = redemption_set_national_flag
    pyserver.HANDLERS['updatePlayerLBSData'] = redemption_update_lbs
    print('[server] ROS Redemption: Profile rename & national flag handlers registered in pyserver.HANDLERS!', flush=True)
except Exception as e:
    print('[server] Error registering profile controls:', e, flush=True)

# --------------------------------------------------------------------------
# ROS REDEMPTION: MASTER LEADERBOARD & RPC HANDLERS
# --------------------------------------------------------------------------
# Fixes empty rank list, unhandled rlPlayerCards, weapon proficiencies,
# credit scores, intimate relations, friends list, rooms, and mall purchases.
# --------------------------------------------------------------------------
try:
    from backend_server.features import ranking
    from backend_server import pyserver

    REDEMPTION_LEGENDS = [
        {
            'gid': 10000010, 'nickname': 'PhantomSniper', 'level': 35, 'characterType': 10002,
            'score': 2850, 'nationalFlag': 'PH', 'portrait': '0', 'fights': 180, 'wins': 120,
            'kills': 850, 'deaths': 60, 'top5': 145, 'killCombo': 24, 'headShot': 272, 'hitCount': 890
        },
        {
            'gid': 10000011, 'nickname': 'RedemptionKing', 'level': 32, 'characterType': 10001,
            'score': 2740, 'nationalFlag': 'PH', 'portrait': '0', 'fights': 175, 'wins': 110,
            'kills': 780, 'deaths': 65, 'top5': 138, 'killCombo': 22, 'headShot': 245, 'hitCount': 810
        },
        {
            'gid': 10000012, 'nickname': 'GhostRider_PH', 'level': 30, 'characterType': 10002,
            'score': 2620, 'nationalFlag': 'PH', 'portrait': '0', 'fights': 160, 'wins': 98,
            'kills': 710, 'deaths': 62, 'top5': 125, 'killCombo': 20, 'headShot': 210, 'hitCount': 720
        },
        {
            'gid': 10000013, 'nickname': 'ShadowHunter', 'level': 28, 'characterType': 10001,
            'score': 2510, 'nationalFlag': 'US', 'portrait': '0', 'fights': 150, 'wins': 89,
            'kills': 640, 'deaths': 61, 'top5': 118, 'killCombo': 19, 'headShot': 192, 'hitCount': 650
        },
        {
            'gid': 10000014, 'nickname': 'ManilaGhost', 'level': 27, 'characterType': 10002,
            'score': 2430, 'nationalFlag': 'PH', 'portrait': '0', 'fights': 142, 'wins': 82,
            'kills': 590, 'deaths': 60, 'top5': 110, 'killCombo': 18, 'headShot': 175, 'hitCount': 600
        },
        {
            'gid': 10000015, 'nickname': 'ApexPredator', 'level': 26, 'characterType': 10001,
            'score': 2350, 'nationalFlag': 'SG', 'portrait': '0', 'fights': 135, 'wins': 76,
            'kills': 530, 'deaths': 59, 'top5': 102, 'killCombo': 17, 'headShot': 150, 'hitCount': 540
        },
        {
            'gid': 10000016, 'nickname': 'CyberViper', 'level': 25, 'characterType': 10002,
            'score': 2260, 'nationalFlag': 'PH', 'portrait': '0', 'fights': 128, 'wins': 71,
            'kills': 490, 'deaths': 57, 'top5': 95, 'killCombo': 16, 'headShot': 135, 'hitCount': 490
        },
        {
            'gid': 10000017, 'nickname': 'DragonSlayer', 'level': 24, 'characterType': 10001,
            'score': 2180, 'nationalFlag': 'JP', 'portrait': '0', 'fights': 120, 'wins': 65,
            'kills': 440, 'deaths': 55, 'top5': 88, 'killCombo': 15, 'headShot': 115, 'hitCount': 440
        },
        {
            'gid': 10000018, 'nickname': 'BulletStorm', 'level': 23, 'characterType': 10002,
            'score': 2090, 'nationalFlag': 'KR', 'portrait': '0', 'fights': 115, 'wins': 60,
            'kills': 410, 'deaths': 55, 'top5': 82, 'killCombo': 14, 'headShot': 102, 'hitCount': 410
        },
        {
            'gid': 10000019, 'nickname': 'SilentAssassin', 'level': 22, 'characterType': 10001,
            'score': 1980, 'nationalFlag': 'PH', 'portrait': '0', 'fights': 110, 'wins': 55,
            'kills': 380, 'deaths': 55, 'top5': 75, 'killCombo': 13, 'headShot': 95, 'hitCount': 380
        },
        {
            'gid': 10000020, 'nickname': 'Valkyrie_PH', 'level': 21, 'characterType': 10002,
            'score': 1890, 'nationalFlag': 'PH', 'portrait': '0', 'fights': 105, 'wins': 50,
            'kills': 350, 'deaths': 55, 'top5': 70, 'killCombo': 12, 'headShot': 80, 'hitCount': 350
        },
        {
            'gid': 10000021, 'nickname': 'IronClad', 'level': 20, 'characterType': 10001,
            'score': 1780, 'nationalFlag': 'TH', 'portrait': '0', 'fights': 100, 'wins': 45,
            'kills': 320, 'deaths': 55, 'top5': 65, 'killCombo': 11, 'headShot': 70, 'hitCount': 320
        },
        {
            'gid': 10000022, 'nickname': 'WarMachine', 'level': 19, 'characterType': 10002,
            'score': 1690, 'nationalFlag': 'ID', 'portrait': '0', 'fights': 95, 'wins': 40,
            'kills': 290, 'deaths': 55, 'top5': 60, 'killCombo': 10, 'headShot': 60, 'hitCount': 290
        },
        {
            'gid': 10000023, 'nickname': 'HavocBringer', 'level': 18, 'characterType': 10001,
            'score': 1580, 'nationalFlag': 'MY', 'portrait': '0', 'fights': 90, 'wins': 36,
            'kills': 260, 'deaths': 54, 'top5': 55, 'killCombo': 9, 'headShot': 52, 'hitCount': 260
        },
        {
            'gid': 10000024, 'nickname': 'BloodHound', 'level': 17, 'characterType': 10002,
            'score': 1470, 'nationalFlag': 'VN', 'portrait': '0', 'fights': 85, 'wins': 32,
            'kills': 230, 'deaths': 53, 'top5': 50, 'killCombo': 8, 'headShot': 44, 'hitCount': 230
        },
        {
            'gid': 10000025, 'nickname': 'NightStalker', 'level': 16, 'characterType': 10001,
            'score': 1360, 'nationalFlag': 'PH', 'portrait': '0', 'fights': 80, 'wins': 28,
            'kills': 200, 'deaths': 52, 'top5': 45, 'killCombo': 7, 'headShot': 36, 'hitCount': 200
        }
    ]

    LEGENDS_BY_GID = {leg['gid']: leg for leg in REDEMPTION_LEGENDS}

    TOP_PLATOONS = [
        {'teamID': 1, 'name': 'DEV', 'exp': 8500, 'act': 100, 'level': 5, 'memberCnt': 15, 'memberMax': 20, 'sumScore': 12500, 'leaderName': 'sean', 'logo': '1', 'logoType': 3, 'nation': 'PH'},
        {'teamID': 2, 'name': 'REDEMPTION_ELITE', 'exp': 6200, 'act': 80, 'level': 4, 'memberCnt': 12, 'memberMax': 20, 'sumScore': 9800, 'leaderName': 'PhantomSniper', 'logo': '2', 'logoType': 3, 'nation': 'PH'},
        {'teamID': 3, 'name': 'MANILA_GHOSTS', 'exp': 5100, 'act': 70, 'level': 4, 'memberCnt': 10, 'memberMax': 20, 'sumScore': 8400, 'leaderName': 'ManilaGhost', 'logo': '3', 'logoType': 3, 'nation': 'PH'},
        {'teamID': 4, 'name': 'PH_CYBER_WARRIORS', 'exp': 4300, 'act': 60, 'level': 3, 'memberCnt': 8, 'memberMax': 20, 'sumScore': 7200, 'leaderName': 'CyberViper', 'logo': '4', 'logoType': 3, 'nation': 'PH'},
        {'teamID': 5, 'name': 'ASIAN_LEGENDS', 'exp': 3800, 'act': 50, 'level': 3, 'memberCnt': 8, 'memberMax': 20, 'sumScore': 6500, 'leaderName': 'ApexPredator', 'logo': '5', 'logoType': 3, 'nation': 'SG'}
    ]

    def make_player_card(gid, db=None):
        gid = int(gid)
        if gid in LEGENDS_BY_GID:
            leg = LEGENDS_BY_GID[gid]
            return {
                'gid': gid,
                'nickname': leg['nickname'],
                'level': leg['level'],
                'characterType': leg['characterType'],
                'score': leg['score'],
                'nationalFlag': leg['nationalFlag'],
                'portrait': leg['portrait'],
                'badge': 0,
                'identifyTagID': 0,
                'isOnline': True,
                'inTeam': False,
                'records': {}
            }
        if db:
            try:
                row = db.character(gid)
                if row:
                    card = ranking.public_profile(row, gid)
                    card.setdefault('portrait', '0')
                    card.setdefault('badge', 0)
                    card.setdefault('identifyTagID', 0)
                    card.setdefault('isOnline', True)
                    card.setdefault('inTeam', False)
                    return card
            except Exception:
                pass
        return {
            'gid': gid,
            'nickname': f'Player_{gid}',
            'level': 1,
            'characterType': 10001,
            'score': 100,
            'nationalFlag': 'PH',
            'portrait': '0',
            'badge': 0,
            'identifyTagID': 0,
            'isOnline': True,
            'inTeam': False,
            'records': {}
        }

    def redemption_player_cards(server, args, kwargs):
        try:
            seq = 0
            gids = []
            props = []
            if len(args) >= 3 and isinstance(args[1], (list, tuple)):
                seq = int(args[0])
                gids = args[1]
                props = args[2] if len(args) > 2 else []
            elif len(args) >= 2 and isinstance(args[0], (list, tuple)):
                gids = args[0]
                props = args[1]
            elif len(args) == 1 and isinstance(args[0], (list, tuple)):
                gids = args[0]
            elif len(args) >= 1:
                try:
                    seq = int(args[0])
                except (ValueError, TypeError):
                    pass
                if len(args) > 1 and isinstance(args[1], (list, tuple)):
                    gids = args[1]

            cards = {}
            db_conn = getattr(server.account, 'db', None)
            for gid_val in gids:
                try:
                    gid = int(gid_val)
                except (ValueError, TypeError):
                    continue
                card = make_player_card(gid, db_conn)
                cards[str(gid)] = card
                cards[gid] = card

            callbacks = []
            if seq:
                callbacks.append({'method': 'rlWebReply', 'args': [seq, cards]})
            callbacks.append({'method': 'onGetPlayerData', 'args': [0, cards]})
            return {
                'handled': True,
                'ok': True,
                'callbacks': callbacks
            }
        except Exception as e:
            print(f"[server] Error in rlPlayerCards: {e}", flush=True)
            return {'handled': True, 'ok': False}

    def make_legend_row(leg, rank_type):
        kind = ranking.board_kind(rank_type)
        if kind == 'winning':
            val = leg['wins']
        elif kind == 'killing' or kind == 'weapon':
            val = leg['kills']
        else:
            val = leg['score']

        fights = max(1, leg['fights'])
        deaths = max(1, leg['deaths'])
        hits = max(1, leg['hitCount'])

        return {
            'winRate': round(float(leg['wins']) / fights, 4),
            'topFiveCount': leg['top5'],
            'topFiveRate': round(float(leg['top5']) / fights, 4),
            'killDeathRate': round(float(leg['kills']) / deaths, 2),
            'killCombo': leg['killCombo'],
            'headshotRate': round(float(leg['headShot']) / hits, 4),
            'value': val,
            'gid': leg['gid'],
            'nickname': leg['nickname'],
            'identifyTagID': 0,
            'nationalFlag': leg['nationalFlag']
        }

    def custom_ranking_board(self, rank_type):
        kind = ranking.board_kind(rank_type)
        now = int(time.time())
        if kind == 'team':
            rows = []
            for i, pl in enumerate(TOP_PLATOONS):
                row = dict(pl)
                row['rank'] = i + 1
                row['idx'] = i
                rows.append(row)
            return (now, rows)

        db_rows = []
        try:
            chars = self.account.db.characters(server_id=self.server_id())
            for c in chars:
                entry = ranking.player_row(c, rank_type)
                if entry is not None:
                    db_rows.append(entry)
                else:
                    lobby = ranking.lobby_of(c)
                    score = int(lobby.get('rankScore') or 100)
                    db_rows.append({
                        'winRate': 0.0,
                        'topFiveCount': 0,
                        'topFiveRate': 0.0,
                        'killDeathRate': 0.0,
                        'killCombo': 0,
                        'headshotRate': 0.0,
                        'value': score if kind == 'force' else 0,
                        'gid': int(c['gid']),
                        'nickname': c['nickname'],
                        'identifyTagID': 0,
                        'nationalFlag': ranking.national_flag(lobby)
                    })
        except Exception as e:
            print("[server] Error reading db characters for ranking:", e, flush=True)

        legend_rows = [make_legend_row(leg, rank_type) for leg in REDEMPTION_LEGENDS]
        all_rows = db_rows + legend_rows
        seen_gids = set()
        deduped = []
        for r in all_rows:
            if r['gid'] not in seen_gids:
                seen_gids.add(r['gid'])
                deduped.append(r)

        deduped.sort(key=lambda r: (-r['value'], r['gid']))
        for i, r in enumerate(deduped):
            r['rank'] = i + 1
            r['idx'] = i

        return (now, deduped)

    def custom_ranking_mine(self, data, params):
        rank_type = ranking.int_param(params, 'rank_type')
        kind = ranking.board_kind(rank_type)
        if kind == 'team':
            return {
                'rank_type': rank_type,
                'kind': kind,
                'info': self._my_team_rank(rank_type)
            }
        version, rows = self.board(rank_type)
        for index, entry in enumerate(rows):
            if entry['gid'] == self.account.gid:
                info = dict(ranking.my_columns(entry, kind), rank=index + 1)
                return {'rank_type': rank_type, 'kind': kind, 'info': info}
        return {
            'rank_type': rank_type,
            'kind': kind,
            'info': {'rank': 0, 'col-3': 0, 'col-4': 0, 'col-5': 0, 'col-6': 0}
        }

    ranking.RankingFeature.board = custom_ranking_board
    ranking.RankingFeature.action_mine = custom_ranking_mine

    def redemption_weapons_proficiency(server, args, kwargs):
        gid = int(args[0]) if args else server.account.gid
        stats = {}
        try:
            row = server.account.db.character(gid)
            if row:
                lobby = ranking.lobby_of(row)
                stats = lobby.get('weaponStats') or {}
        except Exception:
            pass
        if not stats:
            stats = {
                '1002': {'fired': 120, 'kills': 8, 'damage': 750, 'hits': 45},
                '1017': {'fired': 90, 'kills': 5, 'damage': 518, 'hits': 22},
                '1009': {'fired': 150, 'kills': 14, 'damage': 1458, 'hits': 65},
                '1008': {'fired': 85, 'kills': 11, 'damage': 1024, 'hits': 38}
            }
        return {
            'handled': True,
            'ok': True,
            'callbacks': [{'method': 'getHighestProficiencyWeaponsCB', 'args': [stats]}]
        }

    def redemption_credit_score(server, args, kwargs):
        return {
            'handled': True,
            'ok': True,
            'callbacks': [{'method': 'queryCreditScoreCB', 'args': [100]}]
        }

    def redemption_intimate_info(server, args, kwargs):
        return {
            'handled': True,
            'ok': True,
            'callbacks': [{'method': 'onUpdateIntimateRelationship', 'args': [{}, []]}]
        }

    def redemption_friend_data(server, args, kwargs):
        if 'getFriendList' in pyserver.HANDLERS:
            return pyserver.HANDLERS['getFriendList'](server, args, kwargs)
        return {
            'handled': True,
            'ok': True,
            'callbacks': [{'method': 'rlFriend', 'args': ['onGetFriendList', 2, [], {}]}]
        }

    def redemption_room_count(server, args, kwargs):
        return {
            'handled': True,
            'ok': True,
            'callbacks': [{'method': 'onRequestRoomCountInfo', 'args': [0, 0]}]
        }

    def redemption_room_list(server, args, kwargs):
        return {
            'handled': True,
            'ok': True,
            'callbacks': [{'method': 'onRequestRoomListInfo', 'args': [[]]}]
        }

    def redemption_combat_abstract(server, args, kwargs):
        return {
            'handled': True,
            'ok': True,
            'callbacks': [{'method': 'onGetCombatData', 'args': [{}]}]
        }

    def redemption_noop(server, args, kwargs):
        return {'handled': True, 'ok': True, 'callbacks': []}

    def redemption_check_battle_times(server, args, kwargs):
        return {
            'handled': True,
            'ok': True,
            'callbacks': [{'method': 'onCheckBattleTimes', 'args': [1, 1]}]
        }

    def redemption_recall_progress(server, args, kwargs):
        return {
            'handled': True,
            'ok': True,
            'callbacks': [{'method': 'onGetRecallProgress', 'args': [0, 0]}]
        }

    def redemption_recalled_friends(server, args, kwargs):
        return {
            'handled': True,
            'ok': True,
            'callbacks': [{'method': 'onGetRecalledFriends', 'args': [[]]}]
        }

    def redemption_buy_mall_good(server, args, kwargs):
        try:
            goods_id = int(args[0]) if args else 0
            count = int(args[1]) if len(args) > 1 else 1
            item_id = int(kwargs.get('item') or goods_id)
            currency_id = int(kwargs.get('currency_id') or 2)
            price = int(kwargs.get('price') or 0) * count

            account = server.account
            data_out = {}
            with account.db.transaction() as conn:
                with account.edit_in(conn) as data:
                    try:
                        account.spend(data, currency_id, price, f"store:{goods_id}")
                    except Exception:
                        pass
                    account.add_item(data, item_id, count)
                    for extra in kwargs.get('items', []):
                        account.add_item(data, int(extra), 1)
                    data_out = dict(data)

            return {
                'handled': True,
                'ok': True,
                'callbacks': [
                    {'method': 'onBuyMallGood', 'args': [goods_id, count, [item_id], currency_id, price]}
                ],
                'props': {
                    'wallet': data_out.get('wallet', {})
                },
                'tip': 'Purchase successful!'
            }
        except Exception as e:
            print(f"[server] Error in buyMallGood: {e}", flush=True)
            return {'handled': True, 'ok': False}

    def redemption_set_portrait(server, args, kwargs):
        portrait = str(args[0]) if args else '0'
        try:
            account = server.account
            with account.db.transaction() as conn:
                row = conn.execute("SELECT lobby FROM characters WHERE gid = ?", (account.gid,)).fetchone()
                if row:
                    lobby = json.loads(row['lobby'] or '{}')
                    lobby['portrait'] = portrait
                    account.db.update_character_in(conn, account.gid, lobby=lobby)
        except Exception as e:
            print("[server] Error updating portrait:", e, flush=True)
        return {
            'handled': True,
            'ok': True,
            'callbacks': [
                {'method': 'onSetPortrait', 'args': [0, portrait]}
            ],
            'props': {'portrait': portrait},
            'tip': 'Portrait updated successfully!'
        }

    def redemption_dts_award(server, args, kwargs):
        level = args[0] if args else 1
        items = kwargs.get('items', [])
        try:
            account = server.account
            with account.db.transaction() as conn:
                with account.edit_in(conn) as data:
                    for it in items:
                        account.add_item(data, int(it), 1)
        except Exception as e:
            print("[server] Error adding dts award items:", e, flush=True)
        return {
            'handled': True,
            'ok': True,
            'callbacks': [
                {'method': 'onRequestDtsLevelAward', 'args': [0, level]}
            ],
            'tip': 'Award claimed successfully!'
        }

    REDEMPTION_RPC_HANDLERS = {
        'rlPlayerCards': redemption_player_cards,
        'getHighestProficiencyWeapons': redemption_weapons_proficiency,
        'queryCreditScore': redemption_credit_score,
        'requestIntimateRelationshipInfo': redemption_intimate_info,
        'requestFriendData': redemption_friend_data,
        'requestRoomCountInfo': redemption_room_count,
        'requestRoomListInfo': redemption_room_list,
        'requireCombatAbstract': redemption_combat_abstract,
        'reqPayedPartnerRel': redemption_noop,
        'getRecallProgress': redemption_recall_progress,
        'getRecalledFriends': redemption_recalled_friends,
        'requestShareAddtionShow': redemption_noop,
        'requestShareLimit': redemption_noop,
        'dhGuardReport': redemption_noop,
        'checkBattleTimes': redemption_check_battle_times,
        'changeOccupation': redemption_noop,
        'rlSettleDepot': redemption_noop,
        'finishRetAct527TaskFromClient': redemption_noop,
        'updateEntertainNewBadge': redemption_noop,
        'buyMallGood': redemption_buy_mall_good,
        'buyMallGoodInAppearanceMall': redemption_buy_mall_good,
        'setPortrait': redemption_set_portrait,
        'requestDtsLevelAward': redemption_dts_award,
        'queryAvailableBattleGift': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': [{'method': 'onQueryAvailableBattleGift', 'args': [a[0] if a else 0, []]}]},
        'queryAvailableConvertItem': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': [{'method': 'onQueryAvailableConvertItem', 'args': [[]]}]},
        'queryAvailableExchangeItem': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': [{'method': 'onQueryAvailableExchangeItem', 'args': [[]]}]},
        'getOpenMaintenanceFightTipFlag': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': [{'method': 'onGetOpenMaintenanceFightTipFlag', 'args': [False]}]},
        'queryAssistantRedPoint': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': [{'method': 'onQueryAssistantRedPoint', 'args': [{}]}]},
        'queryAvailableActivity': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': [{'method': 'onQueryAvailableActivity', 'args': [[]]}]},
        'queryAvailableAdvertisement': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': [{'method': 'onQueryAvailableAdvertisement', 'args': [[]]}]},
        'queryBlackFriday2019LeftTime': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': [{'method': 'onQueryBlackFriday2019LeftTime', 'args': [0]}]},
        'queryBlackMarketInfo': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': [{'method': 'onUpdateBlackMarketInfo', 'args': [{}]}]},
        'queryTimerUseProp': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': [{'method': 'onGetTimerUseProp', 'args': [[]]}]},
        'changeTantanSex': redemption_noop,
        'changeTantanPicCount': redemption_noop,
        'updateIsIntimateRelationshipVisibleInTeam': redemption_noop,
        'refreshSpecifiedTimeLoginTaskEvent': redemption_noop,
        'requestFilePickerToken': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': [{'method': 'onRequestFilePickerToken', 'args': ['token']}]},
        'requestPackageUUID': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': [{'method': 'onRequestPackageUUID', 'args': ['uuid']}]},
        'requestRecordUSRecomendOnlineLog': redemption_noop,
        'rlActivityState': redemption_noop,
        'tryClickAccumulateCharge': redemption_noop,
        'onUIDtsLevelUpShown': redemption_noop,
    }

    for rpc_name, fn in REDEMPTION_RPC_HANDLERS.items():
        pyserver.HANDLERS[rpc_name] = fn

    print(f'[server] ROS Redemption: Master Leaderboards & all {len(REDEMPTION_RPC_HANDLERS)} RPC handlers active!', flush=True)
except Exception as e:
    print('[server] Error installing master leaderboard and RPC handlers:', e, flush=True)


