import sqlite3

conn = sqlite3.connect(r"C:\DieHardROS\local_update\server_data\accounts.db")
cur = conn.cursor()
cur.execute("PRAGMA table_info(mails);")
for col in cur.fetchall():
    print(col)

cur.execute("SELECT * FROM mails LIMIT 5;")
for row in cur.fetchall():
    print(row)
conn.close()

