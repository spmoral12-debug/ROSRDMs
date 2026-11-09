import sqlite3, json

for db_path in [r"C:\DieHardROS\local_update\server_data\accounts.db",
                r"C:\DieHardROS\runtime\app\local_update\server_data\accounts.db",
                r"C:\DieHardROS\ROS_Redemption_Server_Package\local_update\server_data\accounts.db"]:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT id, gid, title, props FROM mails WHERE deleted = 0")
    rows = c.fetchall()
    print("DB:", db_path, "Mails:", len(rows))
    for r in rows:
        print(" ", r)
    conn.close()

