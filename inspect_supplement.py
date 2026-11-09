import dis, marshal, types, os

for name in [r"C:\DieHardROS\ROS_Redemption_Server_Package\backend_server\supplement_rpc.pyc",
             r"C:\DieHardROS\ROS_Redemption_Server_Package\backend_server\supplement_catalog.pyc",
             r"C:\DieHardROS\ROS_Redemption_Server_Package\backend_server\features\supplement.pyc"]:
    if not os.path.exists(name):
        print("Not found:", name)
        continue
    print("=== FILE:", name)
    with open(name, "rb") as f:
        data = f.read()
    # Find marshal header
    for offset in [4, 8, 12, 16]:
        try:
            co = marshal.loads(data[offset:])
            print(f"Loaded with offset {offset}!")
            print("co_names:", co.co_names)
            for c in co.co_consts:
                if isinstance(c, types.CodeType):
                    print("  func:", c.co_name, c.co_varnames)
            break
        except Exception as e:
            pass
