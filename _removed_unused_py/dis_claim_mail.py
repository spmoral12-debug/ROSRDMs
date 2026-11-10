import marshal, types, dis

with open(r"C:\DieHardROS\ROS_Redemption_Server_Package\backend_server\chat.pyc", "rb") as f:
    co = marshal.loads(f.read()[16:])

def dump_named(c, name):
    for sub in c.co_consts:
        if isinstance(sub, types.CodeType):
            if sub.co_name == name:
                print(f"=== {sub.co_name} ({sub.co_varnames}) ===")
                dis.dis(sub)
                return
            dump_named(sub, name)

dump_named(co, "get_award_from_mail")
dump_named(co, "claim_mail_in")
dump_named(co, "mail_detail")

