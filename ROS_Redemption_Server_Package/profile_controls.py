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


@rpc("appearanceCultivateCompound")
def cultivate_compound(server, args, kwargs):
    src_id = int(args[0]) if len(args) > 0 else 0
    target_id = int(args[1]) if len(args) > 1 else 0
    flag = int(args[2]) if len(args) > 2 else 0
    if not target_id:
        raise AccountError("bad_item", "Invalid target item.")
    account = server.account
    try:
        with account.db.transaction() as conn:
            with account.edit_in(conn) as data:
                if src_id:
                    try:
                        account.remove_item(data, src_id, 1)
                    except Exception:
                        pass
                try:
                    account.spend(data, 1001, 1000, f"cultivate:{target_id}")
                except Exception:
                    pass
                account.add_item(data, target_id, 1)
    except Exception as error:
        raise AccountError("cultivate_error", str(error))
    return {
        "callbacks": [{"method": "onAppearanceCultivateCompound", "args": [target_id]}],
        "tip": "Tune successful!"
    }


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


