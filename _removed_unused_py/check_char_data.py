import sqlite3, json

db = r'C:\DieHardROS\local_update\server_data\accounts.db'
conn = sqlite3.connect(db)
cur = conn.cursor()

cur.execute("SELECT data FROM character_data WHERE gid = 10000002")
row = cur.fetchone()
if row:
    d = json.loads(row[0])
    print("character_data keys:", list(d.keys()))
    # Check if there is currency or diamond in d
    for k, v in d.items():
        if any(w in k.lower() for w in ['diamond', 'gold', 'yuanbao', 'money', 'wallet', 'currency', 'coin']):
            print(f"Found currency key {k}: {v}")
conn.close()

