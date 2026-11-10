import sqlite3

conn = sqlite3.connect(r"C:\DieHardROS\local_update\server_data\accounts.db")
cur = conn.cursor()
cur.execute("SELECT id, gid, title, props, unread FROM mails WHERE gid=10000001;")
for row in cur.fetchall():
    print(row)
conn.close()

