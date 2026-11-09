import sqlite3, json, os

db_paths = [
    r"C:\DieHardROS\local_update\server_data\accounts.db",
    r"C:\DieHardROS\runtime\app\local_update\server_data\accounts.db",
    r"C:\DieHardROS\ROS_Redemption_Server_Package\local_update\server_data\accounts.db"
]

mail_fixes = {
    7: json.dumps([[200001, 25000], [201001, 1444444]]),
    8: json.dumps([[200001, 25000], [201001, 1000]]),
    23: json.dumps([[200001, 100000], [201001, 50000]]),
    26: json.dumps([[200001, 500000], [201001, 100000]])
}

for p in db_paths:
    if os.path.exists(p):
        conn = sqlite3.connect(p)
        c = conn.cursor()
        for mid, props in mail_fixes.items():
            c.execute("UPDATE mails SET props = ? WHERE id = ?", (props, mid))
        conn.commit()
        conn.close()
        print("Restored reward props in", p)

print("Mail rewards fully restored!")

