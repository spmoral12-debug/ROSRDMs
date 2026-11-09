import sqlite3
import json

db_path = r"C:\DieHardROS\local_update\server_data\accounts.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("UPDATE wallets SET freeYuanbao = 100000, payYuanbao = 100000, gp = 500000 WHERE gid = 10000002")
ph_data = json.dumps({"country": "PH", "nation": "PH", "flag": "PH"})
c.execute("UPDATE characters SET lobby = ? WHERE gid = 10000002", (ph_data,))
conn.commit()

print("Wallet:", c.execute("SELECT gid, freeYuanbao, payYuanbao, gp FROM wallets WHERE gid=10000002").fetchone())
print("Char:", c.execute("SELECT gid, nickname, lobby FROM characters WHERE gid=10000002").fetchone())
conn.close()

