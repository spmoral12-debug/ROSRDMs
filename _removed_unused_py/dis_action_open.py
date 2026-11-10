import dis, marshal, types

with open(r"C:\DieHardROS\ROS_Redemption_Server_Package\backend_server\features\supplement.pyc", "rb") as f:
    co = marshal.loads(f.read()[16:])

def dump_action_open(c):
    for sub in c.co_consts:
        if isinstance(sub, types.CodeType):
            if sub.co_name == "action_open":
                print(f"=== {sub.co_name} ({sub.co_varnames}) ===")
                dis.dis(sub)
                return
            dump_action_open(sub)

dump_action_open(co)

