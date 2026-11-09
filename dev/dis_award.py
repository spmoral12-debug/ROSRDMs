import marshal, types, dis

with open(r"C:\DieHardROS\ROS_Redemption_Server_Package\backend_server\chat.pyc", "rb") as f:
    co = marshal.loads(f.read()[16:])

def dump_mail_award(c):
    for sub in c.co_consts:
        if isinstance(sub, types.CodeType):
            if sub.co_name == "MailServer":
                for sub2 in sub.co_consts:
                    if isinstance(sub2, types.CodeType) and sub2.co_name == "award":
                        print(f"=== {sub2.co_name} ({sub2.co_varnames}) ===")
                        dis.dis(sub2)
                        return
            dump_mail_award(sub)

dump_mail_award(co)

