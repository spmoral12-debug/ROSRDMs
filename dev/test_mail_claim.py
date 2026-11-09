import sys, os

sys.path.insert(0, r"C:\DieHardROS\ROS_Redemption_Server_Package")
from backend_server import database, account, chat

db = database.Database(r"C:\DieHardROS\local_update\server_data\accounts.db")
acc = account.Account(db, 10000002)

ms = chat.MailServer(acc)
# Test detail
detail_res = ms.detail([23])
print("Detail result:", detail_res)

# Test award
award_res = ms.award([23])
print("Award result:", award_res)
