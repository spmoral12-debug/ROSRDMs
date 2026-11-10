import marshal, types, dis

with open(r"C:\DieHardROS\ROS_Redemption_Server_Package\backend_server\chat.pyc", "rb") as f:
    co = marshal.loads(f.read()[16:])

def dump_mail(c):
    for sub in c.co_consts:
        if isinstance(sub, types.CodeType):
            if "mail" in sub.co_name.lower() or "award" in sub.co_name.lower():
                print(f"=== {sub.co_name} ({sub.co_varnames}) ===")
                dis.dis(sub)
            dump_mail(sub)

dump_mail(co)

