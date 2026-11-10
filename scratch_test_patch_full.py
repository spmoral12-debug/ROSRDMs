import sys, os, time, json
os.environ['ROS_GAME_DIR'] = os.getcwd()
sys.path.insert(0, 'server_extracted')

from backend_server.features import ranking, store
from backend_server.account import Account
from backend_server.database import Database
from backend_server import pyserver

db = Database()
acc = Account(db, 10000001)
server = pyserver.LocalPyServer(acc)

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
        for gid_val in gids:
            try:
                gid = int(gid_val)
            except (ValueError, TypeError):
                continue
            card = make_player_card(gid, getattr(server.account, 'db', None))
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
        print(f"[server] Error in rlPlayerCards: {e}")
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
        print("[server] Error reading db characters for ranking:", e)

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

# Install rankings
ranking.RankingFeature.board = custom_ranking_board
ranking.RankingFeature.action_mine = custom_ranking_mine

# Additional RPC handlers
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
    # args: [mallGoodID, count, ..., catalog]
    # kwargs: {item, items, currency_id, price}
    try:
        goods_id = int(args[0]) if args else 0
        count = int(args[1]) if len(args) > 1 else 1
        item_id = int(kwargs.get('item') or goods_id)
        currency_id = int(kwargs.get('currency_id') or 2)
        price = int(kwargs.get('price') or 0) * count

        account = server.account
        with account.db.transaction() as conn:
            with account.edit_in(conn) as data:
                # Spend currency if available
                try:
                    account.spend(data, currency_id, price, f"store:{goods_id}")
                except Exception:
                    pass
                # Add item to depot
                account.add_item(data, item_id, count)
                # Also add any bonus items
                for extra in kwargs.get('items', []):
                    account.add_item(data, int(extra), 1)

        return {
            'handled': True,
            'ok': True,
            'callbacks': [
                {'method': 'onBuyMallGood', 'args': [goods_id, count, [item_id], currency_id, price]}
            ],
            'props': {
                'wallet': data.get('wallet', {})
            },
            'tip': 'Purchase successful!'
        }
    except Exception as e:
        print(f"[server] Error in buyMallGood: {e}")
        return {'handled': True, 'ok': False}

# Register all handlers in pyserver
HANDLERS_TO_REGISTER = {
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
}

for name, fn in HANDLERS_TO_REGISTER.items():
    pyserver.HANDLERS[name] = fn

print(f"Verified all {len(HANDLERS_TO_REGISTER)} handlers successfully registered in pyserver.HANDLERS!")

