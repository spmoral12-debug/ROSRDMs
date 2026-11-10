import dis, marshal, types

with open(r"C:\DieHardROS\ROS_Redemption_Server_Package\backend_server\supplement_rpc.pyc", "rb") as f:
    co = marshal.loads(f.read()[16:])

def dump_func(c, name):
    for sub in c.co_consts:
        if isinstance(sub, types.CodeType):
            if sub.co_name == name:
                print(f"=== {sub.co_name} ({sub.co_varnames}) ===")
                dis.dis(sub)
                return
            dump_func(sub, name)

dump_func(co, "_open_pushes")

