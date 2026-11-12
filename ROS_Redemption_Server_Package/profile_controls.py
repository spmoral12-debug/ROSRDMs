"""Profile RPC handlers shared by the local runner and dedicated server."""
import json
import re
import sqlite3
import time

from backend_server.account import AccountError
from backend_server.database import DatabaseError
from backend_server.pyserver import rpc

FLAG_CODE = re.compile(r"[A-Z]{2}")
RENAME_PRICE = 300
FLAG_RECENT_PRICE = 500
FLAG_OLDER_PRICE = 50
FLAG_PRICE_WINDOW = 7 * 86400


def _profile_row(conn, gid):
    row = conn.execute(
        "SELECT nickname, server_id, lobby FROM characters WHERE gid = ?", (gid,)
    ).fetchone()
    if row is None:
        raise AccountError("no_character", "Create a character first.")
    return row, json.loads(row["lobby"] or "{}")


def _reply(method, args, tip):
    return {"callbacks": [{"method": method, "args": args}], "tip": tip}


@rpc("changeNicknameWithCard")
def change_name(server, args, kwargs):
    account = server.account
    try:
        name = account.db.clean_nickname(args[0] if args else None)
        if len(name) > 16:
            raise AccountError("bad_name", "Use up to 16 characters.")
        if any(not char.isprintable() for char in name):
            raise AccountError("bad_name", "Use printable characters in your name.")
        with account.db.transaction() as conn:
            row, lobby = _profile_row(conn, account.gid)
            if name == row["nickname"]:
                raise AccountError("same_name", "Choose a different name.")
            if conn.execute(
                "SELECT 1 FROM characters WHERE server_id = ? AND gid <> ? "
                "AND created = 1 AND nickname = ? COLLATE NOCASE",
                (row["server_id"], account.gid, name),
            ).fetchone():
                raise AccountError("name_taken", "That name is already taken.")
            if lobby.get("freeNickNameUsed"):
                with account.edit_in(conn) as data:
                    account.charge(data, "diamond", RENAME_PRICE, "nickname_change")
            lobby["freeNickNameUsed"] = True
            account.db.update_character_in(conn, account.gid, nickname=name, lobby=lobby)
    except DatabaseError as error:
        raise AccountError(error.code, error.message) from error
    except sqlite3.IntegrityError as error:
        raise AccountError("name_taken", "That name is already taken.") from error
    return _reply("rlRedemptionNickname", [name], "Name changed.")


@rpc("setNationalFlag")
def change_flag(server, args, kwargs):
    flag = args[0] if args else None
    if not isinstance(flag, str) or not FLAG_CODE.fullmatch(flag):
        raise AccountError("bad_flag", "Choose a flag from the list.")
    account = server.account
    try:
        with account.db.transaction() as conn:
            _, lobby = _profile_row(conn, account.gid)
            previous_time = int(lobby.get("nationalFlagSetTime") or 0)
            if lobby.get("nationalFlag") == flag:
                return _reply("rlRedemptionFlag", [flag, previous_time], "Flag already selected.")
            now = int(time.time())
            if previous_time:
                price = FLAG_RECENT_PRICE if now - previous_time < FLAG_PRICE_WINDOW else FLAG_OLDER_PRICE
                with account.edit_in(conn) as data:
                    account.charge(data, "diamond", price, "flag_change")
            lobby.update(nationalFlag=flag, nationalFlagSetTime=now)
            account.db.update_character_in(conn, account.gid, lobby=lobby)
    except DatabaseError as error:
        raise AccountError(error.code, error.message) from error
    return _reply("rlRedemptionFlag", [flag, now], "Flag changed.")


_TUNE_SOURCES = {
        140032: 140031,  # Nova X2 -> Nova X1
        140033: 140031,  # Nova X3 consumes a spare Nova X1 after unlocking X2
        140035: 140031,  # Supernova -> Nova X1
        140905: 140902,  # Reign of Fire -> 5 Star Ride
        140404: 140403,  # Monster - M2 -> Monster - M1
        140405: 140403,  # Monster - M3 consumes a spare M1 after unlocking M2
        140406: 140404,  # Wild Beast -> Monster - M2
        140013: 140010,  # Thunderbird -> Spark V3
        140024: 140021,  # Storm -> Twister - T1
        142029: 142028,  # Burst Sedan Lv. 2 -> Lv. 1
        142030: 142029,  # Burst Sedan Lv. 3 -> Lv. 2
        140051: 140048,  # Fiery Hunting -> Hunting Path - I
        140046: 140041,  # Brain Freeze -> Frosty Frills - I
        140914: 140911,  # Warjeep lv 4 -> lv 1
        140223: 140221,  # Subjugator T2 -> Subjugator
        140224: 140223,  # Discovery -> Subjugator T2
        140061: 140056,  # Hovering Car Max -> Lv. 1
        142003: 140241,  # Deathmobile -> Burst Buggy - I
        140077: 140076,  # Darksteel Bike Lv. 2 -> Lv. 1
        140214: 140211,  # Pegasus Turbo -> Pegasus - I
        140205: 140202,  # Phoenix -> Blazing Flash A1
        142005: 142004,  # Golden Flash Lv. 2 -> Lv. 1
        142006: 142005,  # Golden Flash Lv. 3 -> Lv. 2
        142012: 142011,  # Shadowfax Kingly -> Noble
        142013: 142012,  # Shadowfax Furious -> Kingly
        142008: 142007,  # Velociraptor Lv. 2 -> Lv. 1
        140237: 142007,  # Velociraptor Lv. 2 (native) -> Lv. 1
        140074: 140073,  # Summer Bicycle Lv. 2 -> Lv. 1
        140064: 140062,  # Dynamic Streamer Lv. 1 -> Base
        140065: 140064,  # Dynamic Streamer MAX -> Lv. 1
}

_TUNE_PREREQUISITES = {140033: 140032, 140035: 140033, 140405: 140404, 140406: 140405}
_TUNE_GOLD = {140032: 2000, 140033: 2000, 140404: 2000, 140405: 2000}


@rpc("appearanceCultivateCompound")
def cultivate_compound(server, args, kwargs):
    target_id = int(args[1]) if len(args) > 1 else 0
    effective_src = _TUNE_SOURCES.get(target_id)
    if effective_src is None:
        raise AccountError("bad_item", "Unsupported Workshop upgrade.")
    account = server.account
    try:
        with account.db.transaction() as conn:
            with account.edit_in(conn) as data:
                depot = data.setdefault("depot", {})
                prerequisite = _TUNE_PREREQUISITES.get(target_id)
                if prerequisite is not None:
                    previous = depot.get(str(prerequisite), {})
                    if int(previous.get("count", 0) or 0) < 1 or previous.get("expires"):
                        raise AccountError("missing_prerequisite", "Unlock the previous upgrade first.")
                src_entry = depot.get(str(effective_src), {})
                source_count = int(src_entry.get("count", 0) or 0)
                if source_count < 2 or src_entry.get("expires"):
                    raise AccountError("missing_duplicate", "You need two permanent copies to upgrade.")

                account.spend(data, 1, _TUNE_GOLD.get(target_id, 1000), f"cultivate:{target_id}")
                src_entry["count"] = source_count - 1
                target = depot.get(str(target_id), {})
                depot[str(target_id)] = {"count": int(target.get("count", 0) or 0) + 1, "expires": 0}
                account.record(data, "vehicle_upgrade", source=effective_src, target=target_id)
                
                equipped = data.setdefault("equipped", {})
                for k, v in list(equipped.items()):
                    if isinstance(v, list) and effective_src in v:
                        equipped[k] = [target_id if x == effective_src else x for x in v]
                    elif v == effective_src:
                        equipped[k] = target_id
                
                # Clear recent_changes so server does not send duplicate items in reply['items']
                server.account.recent_changes = []
    except AccountError:
        raise
    except Exception as error:
        raise AccountError("cultivate_error", str(error))
    return {
        "callbacks": [{"method": "onAppearanceCultivateCompound", "args": [target_id]}],
        "extra": {"workshop_counts": {str(effective_src): source_count - 1,
                                      str(target_id): depot[str(target_id)]["count"]}},
        "tip": "Tune successful!"
    }


# Auto-sanitize account depots on load to clean up duplicate copies & consumed vehicles
try:
    from backend_server.account import Account
    _orig_account_load = getattr(Account, '_load', None)
    if _orig_account_load is not None and not getattr(_orig_account_load, '_dh_sanitized', False):
        def _sanitized_account_load(self, conn):
            data = _orig_account_load(self, conn)
            try:
                if isinstance(data, dict):
                    depot = data.get("depot")
                    if isinstance(depot, dict):
                        changed = False
                        # 1. Evolution pairs cleanup: prune source items if upgraded tier is owned
                        evo_pairs = [
                            ("140032", ("140031",)),
                            ("140033", ("140031",)),
                            ("140035", ("140031",)),
                            ("140905", ("140902",)),
                            ("140406", ("140404", "140403")),
                            ("140405", ("140403",)),
                            ("140404", ("140403",)),
                            ("140013", ("140010",)),
                            ("140024", ("140021",)),
                            ("142030", ("142029", "142028")),
                            ("142029", ("142028",)),
                            ("140051", ("140048",)),
                            ("140046", ("140041",)),
                            ("140914", ("140911",)),
                            ("140224", ("140223", "140221")),
                            ("140223", ("140221",)),
                            ("140061", ("140056",)),
                            ("142003", ("140241",)),
                            ("140077", ("140076",)),
                            ("140214", ("140211",)),
                            ("140205", ("140202",)),
                            ("142006", ("142005", "142004")),
                            ("142005", ("142004",)),
                            ("142013", ("142012", "142011")),
                            ("142012", ("142011",)),
                            ("142008", ("142007",)),
                            ("140237", ("142007",)),
                            ("140074", ("140073",)),
                            ("140065", ("140064", "140062")),
                            ("140064", ("140062",)),
                        ]
                        # Preserved: players own both base and evolved tiers (Lv1 + Lv2).
                        # If upgraded tier is owned but base tier was lost during earlier buggy upgrades, restore base tier:
                        for higher_tier, base_tiers in evo_pairs:
                            if str(higher_tier) in depot or (higher_tier.isdigit() and int(higher_tier) in depot):
                                for base in base_tiers:
                                    if str(base) not in depot and (base.isdigit() and int(base) not in depot):
                                        depot[str(base)] = {"count": 1, "expires": 0}
                                        changed = True
                        # 2. Clamp duplicate permanent cosmetics:
                        for k, v in list(depot.items()):
                            if isinstance(v, dict) and not int(v.get("expires") or 0):
                                try:
                                    iid = int(k)
                                    # Cosmetic hall props: vehicles, weapons, clothes, themes
                                    if v.get("count", 1) > 1 and iid not in _TUNE_SOURCES.values() and iid not in _TUNE_SOURCES and not (200000 <= iid < 300000 or 490000 <= iid < 500000):
                                        v["count"] = 1
                                        changed = True
                                except Exception:
                                    pass
                        if changed:
                            self._save(conn, data)
            except Exception:
                pass
            return data
        _sanitized_account_load._dh_sanitized = True
        Account._load = _sanitized_account_load
except Exception:
    pass

# ==============================================================================
# Training Manual (Brave Book 2) Points & Level Purchases
# ==============================================================================
try:
    from backend_server.features.store import StoreFeature
    from backend_server.features.manual import ManualFeature
    from backend_server.pyserver import LocalPyServer, encode

    _pending_manual_callbacks = []

    _orig_store_action_buy = getattr(StoreFeature, 'action_buy', None)

    if _orig_store_action_buy is not None and not getattr(_orig_store_action_buy, '_dh_manual_points', False):
        def _patched_store_action_buy(self, data, params):
            result = _orig_store_action_buy(self, data, params)
            try:
                goods_id = str(params.get('goods_id', ''))
                item_id = int(params.get('item', 0) or 0)
                items = params.get('items', [])
                count = max(1, int(params.get('count', 1)))

                if isinstance(result, dict):
                    result['ok'] = True
                    result['handled'] = True
                    props = result.setdefault('props', {})
                    if 'wallet' not in props and 'wallet' in data:
                        props['wallet'] = data['wallet']

                is_points = (
                    goods_id == '3002' or
                    item_id == 261011 or
                    261011 in items or
                    '261011' in items or
                    result.get('item') == 261011 or
                    (isinstance(result.get('hall_props'), list) and 261011 in result.get('hall_props'))
                )
                if is_points:
                    points_to_add = 100 * count
                    depot = data.get('depot', {})
                    if '261011' in depot:
                        del depot['261011']

                    manual_feat = ManualFeature(self.account)
                    manual_res = manual_feat.action_add_exp(data, {'exp': points_to_add})
                    manual_cbs = manual_res.get('callbacks', [])
                    season_info = manual_feat.window_info(data.get('manual', {}))
                    extra_cbs = [{'method': 'rlManualSeason', 'args': [season_info]}] + manual_cbs
                    _pending_manual_callbacks.extend(extra_cbs)
            except Exception:
                pass
            return result
        _patched_store_action_buy._dh_manual_points = True
        StoreFeature.action_buy = _patched_store_action_buy

    _orig_manual_action_state = getattr(ManualFeature, 'action_state', None)
    if _orig_manual_action_state is not None and not getattr(_orig_manual_action_state, '_dh_manual_points', False):
        def _patched_manual_action_state(self, data, params):
            try:
                depot = data.get('depot', {})
                if '261011' in depot:
                    entry = depot.pop('261011', {})
                    count = entry.get('count', 1) if isinstance(entry, dict) else int(entry or 1)
                    if count > 0:
                        self._points(data.get('manual', {}), 100 * count)
            except Exception:
                pass
            return _orig_manual_action_state(self, data, params)
        _patched_manual_action_state._dh_manual_points = True
        ManualFeature.action_state = _patched_manual_action_state

    _orig_run_route = getattr(LocalPyServer, '_run_route', None)
    if _orig_run_route is not None and not getattr(_orig_run_route, '_dh_manual_points', False):
        def _patched_run_route(self, method, route, args, kwargs):
            _pending_manual_callbacks.clear()
            reply = _orig_run_route(self, method, route, args, kwargs)
            if _pending_manual_callbacks and isinstance(reply, dict) and 'callbacks' in reply:
                for cb in _pending_manual_callbacks:
                    try:
                        reply['callbacks'].append(encode(cb))
                    except Exception:
                        pass
                _pending_manual_callbacks.clear()
            return reply
        _patched_run_route._dh_manual_points = True
        LocalPyServer._run_route = _patched_run_route
except Exception as e:
    print("[server] Training points patch init error:", e)


# ==============================================================================
# Theme Purchase & Equip RPC Handlers
# ==============================================================================
@rpc("updateDtsHallThemeID", "setDtsHallThemeID")
def rpc_update_dts_hall_theme(server, args, kwargs):
    theme_id = int(args[0]) if args else 0
    account = server.account
    try:
        with account.db.transaction() as conn:
            with account.edit_in(conn) as data:
                equipped = data.setdefault("equipped", {})
                equipped["dtsHallThemeID"] = theme_id
                lobby = data.setdefault("lobby", {})
                lobby["dtsHallThemeID"] = theme_id
                lobby["dhThemeOwn"] = theme_id
    except Exception as error:
        raise AccountError("theme_update_error", str(error))
    return {
        "ok": True,
        "handled": True,
        "props": {"dtsHallThemeID": theme_id},
        "callbacks": [{"method": "onUpdateDtsHallThemeID", "args": [theme_id]}],
        "tip": "Lobby theme updated!" if theme_id else "Lobby theme reset."
    }


@rpc("buyMultipleMallGood")
def rpc_buy_multiple_mall_good(server, args, kwargs):
    account = server.account
    goods_list = kwargs.get('goods') or []
    if not goods_list and args and isinstance(args[0], (list, tuple)):
        goods_list = [{'goods_id': gid, 'item': gid, 'currency_id': 2, 'price': 0} for gid in args[0]]

    all_granted_items = []
    hall_props = []

    try:
        with account.db.transaction() as conn:
            with account.edit_in(conn) as data:
                for g in goods_list:
                    goods_id = str(g.get('goods_id', ''))
                    item_id = int(g.get('item', 0) or goods_id or 0)
                    currency_id = int(g.get('currency_id', 2) or 2)
                    price = max(0, int(g.get('price', 0) or 0))

                    if price > 0:
                        account.spend(data, currency_id, price, f"buy_multiple:{goods_id}")

                    sub_items = g.get('items') or [item_id]
                    for itm in sub_items:
                        itm_id = int(itm)
                        if itm_id:
                            account.add_item(data, itm_id, 1)
                            all_granted_items.append({'item': itm_id, 'count': 1, 'expires': 0})
                            hall_props.append(itm_id)

                wallet = data.get('wallet', {})
    except Exception as error:
        raise AccountError("buy_failed", str(error))

    return {
        "ok": True,
        "handled": True,
        "props": {"wallet": wallet},
        "items": all_granted_items,
        "callbacks": [
            {"method": "onBuyMallGood", "args": [hall_props]},
            {"method": "onBuyMultipleMallGood", "args": [list(args[0]) if args and isinstance(args[0], (list, tuple)) else []]}
        ],
        "tip": "Purchase successful!"
    }


