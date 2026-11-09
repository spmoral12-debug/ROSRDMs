import sqlite3, os

db = r"C:\DieHardROS\local_update\server_data\accounts.db"
if os.path.exists(db):
    conn = sqlite3.connect(db)
    # Gawing malinis ang admin account: 5,000 Diamonds at 50,000 Gold bilang starter
    conn.execute("UPDATE wallets SET freeYuanbao = 5000, payYuanbao = 5000, gp = 50000")
    
    # Siguraduhing PH Flag ang character
    try:
        conn.execute("UPDATE characters SET country = 'PH', nation = 'PH', flag = 'PH'")
    except:
        pass
    conn.commit()
    conn.close()
    print(">>> Wallets at Flags successfully updated in database!")
