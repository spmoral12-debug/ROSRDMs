import sqlite3
import json

db_paths = [
    r"C:\DieHardROS\local_update\server_data\accounts.db",
    r"C:\DieHardROS\ROS_Redemption_Server_Package\local_update\server_data\accounts.db"
]

for p in db_paths:
    print("Checking:", p)
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    cur.execute("SELECT id, to_gid, title, props, is_award_taken FROM mails WHERE to_gid=10000001;")
    for r in cur.fetchall():
        print(f"  Mail #{r[0]} | Title: {r[2]} | Props: {r[3]} | Taken: {r[4]}")
    conn.close()

