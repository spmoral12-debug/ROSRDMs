import marshal, types

with open(r"C:\DieHardROS\ROS_Redemption_Server_Package\backend_server\chat.pyc", "rb") as f:
    co = marshal.loads(f.read()[16:])

print("co_consts:")
for c in co.co_consts:
    if isinstance(c, dict):
        print("dict:", c)
    elif isinstance(c, (list, tuple)):
        for x in c:
            if isinstance(x, dict):
                print("subdict:", x)

