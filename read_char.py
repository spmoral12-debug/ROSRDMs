import sqlite3
import json

conn = sqlite3.connect(r'C:\DieHardROS\runtime\app\local_update\server_data\accounts.db')
c = conn.cursor()
c.execute("PRAGMA table_info(character_data)")
cols = [r[1] for r in c.fetchall()]
print("Columns:", cols)

c.execute("SELECT * FROM character_data")
for row in c.fetchall():
    d = dict(zip(cols, row))
    print("GID:", d.get('gid'))
    for k, v in d.items():
        if k != 'gid':
            print(f"  {k}: {repr(v)[:80]}")

