import json
import os

client_tables_path = r"C:\DieHardROS\ROS_Redemption_Server_Package\local_update\logs\client_tables.json"
with open(client_tables_path, "r", encoding="utf-8") as f:
    ct = json.load(f)

boxes_table = ct.get("tables", {}).get("Supplement", {})

sup_path = r"C:\DieHardROS\ROS_Redemption_Server_Package\backend_server\data\supplement_boxes.json"
with open(sup_path, "r", encoding="utf-8") as f:
    sup = json.load(f)

# Ensure existing pools have 0 days (all permanent)
for pname, pool in sup.get("pools", {}).items():
    for item in pool:
        if "days" in item:
            item["days"] = 0
        if item.get("currency") == "gp" and item.get("amount", 0) < 10000:
            item["amount"] = 10000

# High-tier universal rare items
top_universal_items = [
    {"weight": 15, "item": 120901, "count": 1, "days": 0, "quality": 5, "name": "AK47 - Dragon Gold"},
    {"weight": 15, "item": 120912, "count": 1, "days": 0, "quality": 5, "name": "M4A1 - Laser Star"},
    {"weight": 15, "item": 120928, "count": 1, "days": 0, "quality": 5, "name": "Barrett - Aurora"},
    {"weight": 15, "item": 140935, "count": 1, "days": 0, "quality": 5, "name": "Lamborghini Supercar"},
    {"weight": 15, "item": 140945, "count": 1, "days": 0, "quality": 5, "name": "Cyber Battle Car"},
    {"weight": 20, "item": 140073, "count": 1, "days": 0, "quality": 4, "name": "Summer Bicycle"},
    {"weight": 20, "item": 909042, "count": 1, "days": 0, "quality": 4, "name": "Tango Emote"},
    {"weight": 25, "currency": "diamond", "amount": 1000, "displayItem": 201001},
    {"weight": 25, "currency": "gp", "amount": 50000, "displayItem": 200001}
]

# Build custom pools and box definitions for all 254 boxes
for sid, row in boxes_table.items():
    featured_props = []
    for c in row.get("CarouselParamList", []):
        for m in c.get("DISPLAY_IN_MODEL", []):
            for pid in m.get("DISPLAY_PROP_LIST", []):
                if pid and pid not in featured_props:
                    featured_props.append(pid)
    for g in row.get("GUARANTEE_LIST", []):
        gid = g.get("GUARANTEE_PROP_ID")
        if gid and gid not in featured_props:
            featured_props.append(gid)

    pool_name = f"box_pool_{sid}"
    rare_pool_name = f"rare_pool_{sid}"

    # The box specific rare pool
    rare_entries = []
    for pid in featured_props:
        rare_entries.append({
            "weight": 30,
            "item": pid,
            "count": 1,
            "days": 0,
            "quality": 5
        })
    if not rare_entries:
        rare_entries = [x for x in top_universal_items if "item" in x]

    # The box main pool
    main_entries = list(rare_entries) # high chance of featured items
    main_entries.extend(top_universal_items)

    sup["pools"][pool_name] = main_entries
    sup["pools"][rare_pool_name] = rare_entries

    # Add or update box config
    box_def = sup["boxes"].get(sid, {})
    box_def["name"] = row.get("DISPLAY_SUPPLEMENT_TITLE") or row.get("NAME") or f"Supply Box {sid}"
    box_def["kind"] = "NORMAL_SUPPLEMENT"
    box_def["pool"] = pool_name
    box_def["guarantee"] = {"every": 5, "pool": rare_pool_name}
    box_def["freeEveryHours"] = 24
    box_def["freeTimesPerDay"] = 1

    # Pricing
    if "cost" not in box_def:
        box_def["cost"] = {"currency": "diamond", "amount": 60}
        box_def["multiCost"] = {"currency": "diamond", "amount": 540}
        box_def["multiTimes"] = 10

    sup["boxes"][sid] = box_def

# Save to all target paths
targets = [
    r"C:\DieHardROS\ROS_Redemption_Server_Package\backend_server\data\supplement_boxes.json",
    r"C:\Users\seanj\dev\server_extracted\backend_server\data\supplement_boxes.json"
]

for t in targets:
    os.makedirs(os.path.dirname(t), exist_ok=True)
    with open(t, "w", encoding="utf-8") as f:
        json.dump(sup, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(sup['boxes'])} boxes and {len(sup['pools'])} pools to {t}")

print("Upgrade complete!")

