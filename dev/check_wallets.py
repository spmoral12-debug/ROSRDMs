import sqlite3, os

for p in [r"C:\DieHardROS\local_update\server_data\accounts.db",
          r"C:\DieHardROS\ROS_Redemption_Server_Package\local_update\server_data\accounts.db"]:
    print("Checking:", p, "Exists:", os.path.exists(p))
    if os.path.exists(p):
        conn = sqlite3.connect(p)
        c = conn.cursor()
        c.execute('SELECT a.username, c.gid, c.nickname, w.gp, w.freeYuanbao, w.payYuanbao FROM accounts a JOIN characters c ON a.id = c.account_id JOIN wallets w ON c.gid = w.gid')
        rows = c.fetchall()
        print("Rows in", p)
        for r in rows:
            print(" ", r)
        conn.close()

