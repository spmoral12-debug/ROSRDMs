import dis, marshal, types

with open(r"C:\DieHardROS\ROS_Redemption_Server_Package\backend_server\features\supplement.pyc", "rb") as f:
    co = marshal.loads(f.read()[16:])

print("Top co_names:", co.co_names)
print("Top co_consts:")
for c in co.co_consts:
    if isinstance(c, types.CodeType):
        print("  Code:", c.co_name, c.co_varnames)
        for c2 in c.co_consts:
            if isinstance(c2, types.CodeType):
                print("    Subcode:", c2.co_name, c2.co_varnames)

