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
