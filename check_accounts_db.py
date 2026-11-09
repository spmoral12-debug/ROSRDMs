import sqlite3

for p in [r'C:\DieHardROS\runtime\app\local_update\server_data\accounts.db', r'C:\DieHardROS\local_update\server_data\accounts.db']:
    print('Checking:', p)
    conn = sqlite3.connect(p)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in c.fetchall()]
    print('Tables:', tables)
    for t in tables:
        c.execute("SELECT count(*) FROM " + t)
        print(f'{t}: {c.fetchone()[0]} rows')

