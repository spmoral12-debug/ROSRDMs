import sqlite3, os

# 1. Alamin ang tables sa accounts.db (Mail, Rewards, Wallets)
db = r"C:\DieHardROS\local_update\server_data\accounts.db"
if os.path.exists(db):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    print(">>> MGA DATABASE TABLES SA SERVER:", tables)
    conn.close()

# 2. Hanapin kung paano pinalitan ng original hook ang UILogin logo
unpacked = r"C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py"
if os.path.exists(unpacked):
    with open(unpacked, "r", encoding="utf-8", errors="ignore") as f:
        for idx, line in enumerate(f):
            if any(k in line for k in ["dh_logo", "UILogin", "_dh_screen_survey", "logo_1.png", "bg1.jpg"]):
                print(f"Line {idx+1}: {line.strip()[:100]}")
