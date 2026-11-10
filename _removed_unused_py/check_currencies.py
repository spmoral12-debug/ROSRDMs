import sqlite3, json

db = r'C:\DieHardROS\local_update\server_data\accounts.db'
conn = sqlite3.connect(db)
cur = conn.cursor()

cur.execute("SELECT data FROM character_data WHERE gid = 10000002")
row = cur.fetchone()
if row:
    d = json.loads(row[0])
    print("currencies value:", d.get('currencies'))
conn.close()

