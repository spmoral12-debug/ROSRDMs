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
