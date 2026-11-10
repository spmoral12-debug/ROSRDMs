import dis, marshal, types

with open(r"C:\DieHardROS\ROS_Redemption_Server_Package\backend_server\supplement_rpc.pyc", "rb") as f:
    co = marshal.loads(f.read()[16:])

def dump_code(c, target=""):
    if target and c.co_name != target:
        for sub in c.co_consts:
            if isinstance(sub, types.CodeType):
                dump_code(sub, target)
        return
    print(f"=== {c.co_name} ({c.co_varnames}) ===")
    dis.dis(c)
    for sub in c.co_consts:
        if isinstance(sub, types.CodeType):
            dump_code(sub)

dump_code(co, "_open")

