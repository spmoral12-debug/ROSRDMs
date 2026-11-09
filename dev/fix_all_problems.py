import os
import sys
import json
import sqlite3
import shutil

print("=== EXECUTING ROS REDEMPTION MASTER FIXES ===")

BASE_DIR = r"C:\DieHardROS"

# --------------------------------------------------------------------------
# 1. Update server_patch.py to REMOVE 140073 from dtsBattlegroundPropAppearanceList
# --------------------------------------------------------------------------
sp_paths = [
    os.path.join(BASE_DIR, "local_update", "hot", "server_patch.py"),
    os.path.join(BASE_DIR, "runtime", "app", "local_update", "hot", "server_patch.py"),
    os.path.join(BASE_DIR, "ROS_Redemption_Server_Package", "local_update", "hot", "server_patch.py")
]

for p in sp_paths:
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            code = f.read()

        # Replace the buggy prop assignment
        old_bad = "if not eq.get('dtsBattlegroundPropAppearanceList'):\n                eq['dtsBattlegroundPropAppearanceList'] = [140073]"
        new_good = "eq['dtsBattlegroundPropAppearanceList'] = [x for x in eq.get('dtsBattlegroundPropAppearanceList', []) if x != 140073]"
        if old_bad in code:
            code = code.replace(old_bad, new_good)
        else:
            # Also handle single-line or slight variants
            code = code.replace("eq['dtsBattlegroundPropAppearanceList'] = [140073]", "eq['dtsBattlegroundPropAppearanceList'] = [x for x in eq.get('dtsBattlegroundPropAppearanceList', []) if x != 140073]")

        with open(p, "w", encoding="utf-8") as f:
            f.write(code)
        print("Patched server_patch.py at:", p)

# Also update deploy_master_redemption.py
dmr_path = r"c:\Users\seanj\dev\deploy_master_redemption.py"
if os.path.exists(dmr_path):
    with open(dmr_path, "r", encoding="utf-8") as f:
        dmr_code = f.read()
    dmr_code = dmr_code.replace("eq['dtsBattlegroundPropAppearanceList'] = [140073]", "eq['dtsBattlegroundPropAppearanceList'] = [x for x in eq.get('dtsBattlegroundPropAppearanceList', []) if x != 140073]")
    with open(dmr_path, "w", encoding="utf-8") as f:
        f.write(dmr_code)
    print("Patched deploy_master_redemption.py")

# --------------------------------------------------------------------------
# 2. Deploy Full Upgraded supplement_boxes.json (852KB) to ALL Locations
# --------------------------------------------------------------------------
src_boxes = os.path.join(BASE_DIR, "ROS_Redemption_Server_Package", "backend_server", "data", "supplement_boxes.json")
if not os.path.exists(src_boxes):
    src_boxes = r"c:\Users\seanj\dev\server_extracted\backend_server\data\supplement_boxes.json"

dst_boxes_list = [
    os.path.join(BASE_DIR, "runtime", "app", "backend_server", "data", "supplement_boxes.json"),
    os.path.join(BASE_DIR, "local_update", "server_data", "supplement_boxes.json"),
    os.path.join(BASE_DIR, "runtime", "app", "local_update", "server_data", "supplement_boxes.json"),
    os.path.join(BASE_DIR, "ROS_Redemption_Server_Package", "backend_server", "data", "supplement_boxes.json")
]

if os.path.exists(src_boxes):
    for dst in dst_boxes_list:
        if os.path.abspath(src_boxes).lower() != os.path.abspath(dst).lower():
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src_boxes, dst)
            print(f"Deployed {os.path.getsize(dst):,} bytes supplement_boxes.json -> {dst}")
else:
    print("WARNING: src_boxes not found!", src_boxes)

# --------------------------------------------------------------------------
# 3. Clean Databases: Remove 140073 from props & ensure balanced economy
# --------------------------------------------------------------------------
db_paths = [
    os.path.join(BASE_DIR, "local_update", "server_data", "accounts.db"),
    os.path.join(BASE_DIR, "runtime", "app", "local_update", "server_data", "accounts.db"),
    os.path.join(BASE_DIR, "ROS_Redemption_Server_Package", "local_update", "server_data", "accounts.db")
]

for db_path in db_paths:
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # Update character_data to remove 140073 from dtsBattlegroundPropAppearanceList
        c.execute("SELECT gid, data FROM character_data")
        for row in c.fetchall():
            gid, data_str = row
            try:
                data = json.loads(data_str)
                eq = data.get("equipped", {})
                props = eq.get("dtsBattlegroundPropAppearanceList", [])
                if 140073 in props:
                    props = [x for x in props if x != 140073]
                    eq["dtsBattlegroundPropAppearanceList"] = props
                    data["equipped"] = eq
                    c.execute("UPDATE character_data SET data = ? WHERE gid = ?", (json.dumps(data), gid))
                    print(f"Cleaned 140073 from character_data gid={gid} in {db_path}")
            except Exception as e:
                pass

        # Update characters lobby json
        c.execute("SELECT gid, lobby FROM characters")
        for row in c.fetchall():
            gid, lobby_str = row
            if lobby_str:
                try:
                    lobby = json.loads(lobby_str)
                    app = lobby.get("appearance", {})
                    props = app.get("dtsBattlegroundPropAppearanceList", [])
                    if 140073 in props:
                        app["dtsBattlegroundPropAppearanceList"] = [x for x in props if x != 140073]
                        lobby["appearance"] = app
                        c.execute("UPDATE characters SET lobby = ? WHERE gid = ?", (json.dumps(lobby), gid))
                        print(f"Cleaned 140073 from characters.lobby gid={gid} in {db_path}")
                except Exception as e:
                    pass

        # Clean player_props.json
        c.execute("SELECT gid, username FROM accounts JOIN characters ON accounts.id = characters.account_id WHERE accounts.username != 'Admin_Redemption' AND characters.gid != 10000002")
        non_admins = c.fetchall()
        for gid, user in non_admins:
            # Set starter balance for normal players
            c.execute("UPDATE wallets SET gp = 5000, freeYuanbao = 100, payYuanbao = 0 WHERE gid = ?", (gid,))
            print(f"Normalized economy for player {user} (gid: {gid}): 5,000 GP, 100 Diamonds")

        # Admin Sean stays 999,999,999
        c.execute("UPDATE wallets SET gp = 999999999, freeYuanbao = 999999999, payYuanbao = 999999999 WHERE gid = 10000002")
        print("Admin Sean (10000002) set to 999,999,999 Diamonds & Gold!")

        conn.commit()
        conn.close()

# --------------------------------------------------------------------------
# 4. Clean player_props.json in all folders
# --------------------------------------------------------------------------
props_data = {
    "dtsInGameActionAppearanceIDs": [909042, 909030, 909031, 900001],
    "dtsInGameActionSuitAppearanceIDs": [909042],
    "dtsBattlegroundPropAppearanceList": [],
    "dtsEmojiList": [980001, 980002, 980003]
}

for pp in [
    os.path.join(BASE_DIR, "local_update", "server_data", "player_props.json"),
    os.path.join(BASE_DIR, "runtime", "app", "local_update", "server_data", "player_props.json"),
    os.path.join(BASE_DIR, "ROS_Redemption_Server_Package", "local_update", "server_data", "player_props.json")
]:
    if os.path.exists(os.path.dirname(pp)):
        with open(pp, "w", encoding="utf-8") as f:
            json.dump(props_data, f, indent=2)
        print("Updated player_props.json:", pp)

print("=== ALL FIXES APPLIED SUCCESSFULLY ===")
