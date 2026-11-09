import sqlite3
import json

db_path = r'C:\DieHardROS\local_update\server_data\accounts.db'
con = sqlite3.connect(db_path)
cur = con.cursor()

print("CHARACTERS:")
for r in cur.execute("SELECT * FROM characters").fetchall():
    print(r)

print("\nWALLETS:")
for r in cur.execute("SELECT * FROM wallets").fetchall():
    print(r)

print("\nMAILS:")
for r in cur.execute("SELECT * FROM mails").fetchall():
    print(r)

print("\nACCOUNTS:")
for r in cur.execute("SELECT * FROM accounts").fetchall():
    print(r)

print("\nMETA:")
for r in cur.execute("SELECT * FROM meta").fetchall():
    print(r)
