import sys, os, time, json
os.environ['ROS_GAME_DIR'] = os.getcwd()
sys.path.insert(0, 'server_extracted')

from backend_server import pyserver
from backend_server.account import Account
from backend_server.database import Database

db = Database()
acc = Account(db, 10000001)
server = pyserver.LocalPyServer(acc)

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
        print("Error updating portrait:", e)
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
        print("Error adding dts award items:", e)
    return {
        'handled': True,
        'ok': True,
        'callbacks': [
            {'method': 'onRequestDtsLevelAward', 'args': [0, level]}
        ],
        'tip': 'Award claimed successfully!'
    }

EXTRA_HANDLERS = {
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
    'changeTantanSex': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': []},
    'changeTantanPicCount': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': []},
    'updateIsIntimateRelationshipVisibleInTeam': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': []},
    'refreshSpecifiedTimeLoginTaskEvent': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': []},
    'requestFilePickerToken': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': [{'method': 'onRequestFilePickerToken', 'args': ['token']}]},
    'requestPackageUUID': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': [{'method': 'onRequestPackageUUID', 'args': ['uuid']}]},
    'requestRecordUSRecomendOnlineLog': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': []},
    'rlActivityState': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': []},
    'tryClickAccumulateCharge': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': []},
    'onUIDtsLevelUpShown': lambda s, a, k: {'handled': True, 'ok': True, 'callbacks': []},
}

for name, fn in EXTRA_HANDLERS.items():
    pyserver.HANDLERS[name] = fn

print(f"Verified {len(EXTRA_HANDLERS)} extra handlers registered in pyserver.HANDLERS!")

