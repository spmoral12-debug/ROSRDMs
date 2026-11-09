import json

with open(r"C:\DieHardROS\local_update\logs\rpc_catalog.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for category, rpcs in data.items():
    if "onGetAwardFromMail" in rpcs:
        print("Found in", category, ":", rpcs["onGetAwardFromMail"])
    if "getAwardFromMail" in rpcs:
        print("Found getAwardFromMail in", category, ":", rpcs["getAwardFromMail"])

