import sqlite3
import json

db_paths = [
    r'C:\DieHardROS\runtime\app\local_update\server_data\accounts.db',
    r'C:\DieHardROS\local_update\server_data\accounts.db'
]

for p in db_paths:
    print('Updating database:', p)
    conn = sqlite3.connect(p)
    c = conn.cursor()
    
    # 1. Update characters table (gid 10000002) - column 'lobby'
    c.execute('SELECT lobby FROM characters WHERE gid = 10000002')
    row = c.fetchone()
    if row and row[0]:
        d = json.loads(row[0])
        app = d.setdefault('appearance', {})
        # Equip Summer Bicycle in battleground props
        app['dtsBattlegroundPropAppearanceList'] = [140073]
        # Equip Tango and actions in in-game actions
        app['dtsInGameActionAppearanceIDs'] = [909042, 909030, 909031]
        app['dtsInGameActionSuitAppearanceIDs'] = [909042]
        
        new_json = json.dumps(d)
        c.execute('UPDATE characters SET lobby = ? WHERE gid = 10000002', (new_json,))
        print('  Updated characters appearance for 10000002')
        
    # 2. Update character_data table
    c.execute('SELECT data FROM character_data WHERE gid = 10000002')
    row = c.fetchone()
    if row and row[0]:
        cd = json.loads(row[0])
        eq = cd.setdefault('equipped', {})
        eq['dtsBattlegroundPropAppearanceList'] = [140073]
        eq['dtsInGameActionAppearanceIDs'] = [909042, 909030, 909031]
        eq['dtsInGameActionSuitAppearanceIDs'] = [909042]
        
        new_cd = json.dumps(cd)
        c.execute('UPDATE character_data SET data = ? WHERE gid = 10000002', (new_cd,))
        print('  Updated character_data equipped for 10000002')
        
    conn.commit()
    conn.close()

print('ALL ACCOUNTS.DB UPDATED SUCCESSFULLY!')

