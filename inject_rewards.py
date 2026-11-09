import sqlite3, os, time, json

db = r"C:\DieHardROS\local_update\server_data\accounts.db"
if os.path.exists(db):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    
    # 1. Rekta top-up sa lahat ng wallets: 100,000 Diamonds & 500,000 Gold
    cur.execute("UPDATE wallets SET freeYuanbao = 100000, payYuanbao = 100000, gp = 500000")
    
    # 2. PH Flag sa characters
    try:
        cur.execute("UPDATE characters SET country = 'PH', nation = 'PH', flag = 'PH'")
    except:
        pass
        
    # 3. Magpasok ng starter mail
    now = int(time.time())
    props = json.dumps([{"type": "currency", "payYuanbao": 50000, "freeYuanbao": 50000, "gp": 100000}])
    
    cur.execute("SELECT gid FROM characters")
    gids = [r[0] for r in cur.fetchall()]
    if not gids: gids = [10000001]
    
    for gid in gids:
        cur.execute("""
            INSERT INTO mails (gid, type, title, content, sender, sender_gid, props, created, deadline, unread, deleted)
            VALUES (?, 1, 'ROS Redemption Admin Gift', 'Salamat sa paglalaro! Heto ang iyong admin rewards.', 'System Admin', 0, ?, ?, ?, 1, 0)
        """, (gid, props, now, now + (30*86400)))
        
    conn.commit()
    conn.close()
    print(">>> 100,000 Diamonds at PH Flag matagumpay na nai-save sa database!")
