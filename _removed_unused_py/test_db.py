import os, sqlite3

path = r"C:\DieHardROS\local_update\server_data\accounts.db"
print("File exists:", os.path.exists(path))
try:
    with open(path, "rb") as f:
        print("Read 16 bytes:", f.read(16))
except Exception as e:
    print("Cannot read file:", e)

try:
    uri = f"file:///{path.replace(chr(92), '/')}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    print("Tables:", c.fetchall())
    conn.close()
except Exception as e:
    print("URI connect failed:", e)

try:
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    print("Normal connect Tables:", c.fetchall())
    conn.close()
except Exception as e:
    print("Normal connect failed:", e)

