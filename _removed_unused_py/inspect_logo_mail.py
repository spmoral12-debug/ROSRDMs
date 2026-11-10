import sqlite3

# 1. Tingnan ang schema ng mails table
conn = sqlite3.connect(r"C:\DieHardROS\local_update\server_data\accounts.db")
cur = conn.cursor()
cur.execute("PRAGMA table_info(mails)")
print(">>> MAILS TABLE COLUMNS:", [c[1] for c in cur.fetchall()])
cur.execute("SELECT * FROM mails LIMIT 1")
print(">>> SAMPLE MAIL ROW:", cur.fetchall())
conn.close()

# 2. Basahin ang exact hook logic para sa txt_logo_zjzc.png
with open(r"C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()
for l in lines[7590:7640]:
    print(l, end="")
