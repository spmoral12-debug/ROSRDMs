# -*- coding: utf-8 -*-
from __future__ import print_function
import sqlite3
import json
import time
import os
import sys

# Support Python 2 and Python 3 input
try:
    user_input = raw_input
except NameError:
    user_input = input

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATHS = [
    os.path.join(BASE_DIR, "local_update", "server_data", "accounts.db"),
    os.path.join(BASE_DIR, "ROS_Redemption_Server_Package", "local_update", "server_data", "accounts.db"),
    os.path.join(BASE_DIR, "runtime", "app", "local_update", "server_data", "accounts.db")
]

# Find active DB
active_db = None
for p in DB_PATHS:
    if os.path.exists(p):
        active_db = p
        break

if not active_db:
    print("[ERROR] Hindi makita ang accounts.db sa system!")
    sys.exit(1)

conn = sqlite3.connect(active_db)
cur = conn.cursor()

print("=" * 65)
print("     ROS REDEMPTION - ADMIN IN-GAME REWARD & MAIL SENDER")
print("=" * 65)

# Fetch characters
cur.execute("SELECT c.gid, c.nickname, a.username FROM characters c JOIN accounts a ON a.id = c.account_id ORDER BY c.gid ASC")
chars = cur.fetchall()

if not chars:
    print("[INFO] Walang nakitang characters sa database.")
    conn.close()
    sys.exit(0)

print("\nMGA NAKAREHISTRONG PLAYERS:")
for idx, (gid, nick, user) in enumerate(chars, 1):
    print("  [{0}] {1} (Username: {2} | GID: {3})".format(idx, nick, user, gid))
print("  [A] LAHAT NG PLAYERS (Send to All)")

print("-" * 65)
choice = user_input("Piliin ang padadalhan [1-{0} o A]: ".format(len(chars))).strip().upper()

target_gids = []
if choice == "A":
    target_gids = [r[0] for r in chars]
    target_name = "Lahat ng Players"
else:
    try:
        val = int(choice)
        if 1 <= val <= len(chars):
            target_gids = [chars[val - 1][0]]
            target_name = chars[val - 1][1]
        else:
            print("[ERROR] Invalid choice!")
            conn.close()
            sys.exit(1)
    except:
        print("[ERROR] Invalid input!")
        conn.close()
        sys.exit(1)

# Amount of Diamonds
dia_input = user_input("\nIlang DIAMONDS ang ibibigay? (Default 50000): ").strip()
diamonds = int(dia_input) if dia_input.isdigit() else 50000

# Amount of Gold
gold_input = user_input("Ilang GOLD COINS ang ibibigay? (Default 100000, 0 kung wala): ").strip()
gold = int(gold_input) if gold_input.isdigit() else 100000

# Title
title_input = user_input("Mail Title (Default: 'Admin Special Reward'): ").strip()
mail_title = title_input if title_input else "Admin Special Reward"

# Content
msg_input = user_input("Message/Mensahe (Default: 'Heto ang iyong reward diamonds!'): ").strip()
mail_msg = msg_input if msg_input else "Heto ang iyong reward diamonds! Maraming salamat sa paglalaro."

# Sender
sender_input = user_input("Pangalan ng Sender (Default: 'System Admin'): ").strip()
mail_sender = sender_input if sender_input else "System Admin"

now = int(time.time())
deadline = now + (30 * 86400) # 30 days expiry

# In ROS, 201001 is Diamonds, 200001 is Gold
props_list = []
if diamonds > 0:
    props_list.append([201001, diamonds])
if gold > 0:
    props_list.append([200001, gold])

props_json = json.dumps(props_list)

# Insert into all existing DBs
success_count = 0
for db_file in DB_PATHS:
    if os.path.exists(db_file):
        try:
            db_conn = sqlite3.connect(db_file)
            db_cur = db_conn.cursor()
            for gid in target_gids:
                db_cur.execute("""
                    INSERT INTO mails (gid, type, title, content, sender, sender_gid, props, created, deadline, unread, deleted)
                    VALUES (?, 0, ?, ?, ?, 0, ?, ?, ?, 1, 0)
                """, (gid, mail_title, mail_msg, mail_sender, props_json, now, deadline))
            db_conn.commit()
            db_conn.close()
            success_count += 1
        except Exception as e:
            print("[WARN] Error updating", db_file, ":", e)

print("\n" + "=" * 65)
print(">>> TAGUMPAY! NAI-PADALA NA ANG REWARD VIA IN-GAME MAIL! <<<")
print("Target     :", target_name)
print("Diamonds   :", "{:,}".format(diamonds))
print("Gold       :", "{:,}".format(gold))
print("Mail Title :", mail_title)
print("Sender     :", mail_sender)
print("Database(s):", success_count, "accounts.db updated")
print("=" * 65)
print("Pagbukas ng player sa laro, makikita niya ang Mailbox icon.")
print("I-click lang niya ang 'Claim' para makuha ang mga diamonds!")
print("=" * 65)
