import marshal, types

with open(r"C:\DieHardROS\ROS_Redemption_Server_Package\backend_server\chat.pyc", "rb") as f:
    co = marshal.loads(f.read()[16:])

def list_names(c):
    for sub in c.co_consts:
        if isinstance(sub, types.CodeType):
            print(sub.co_name, sub.co_varnames)
            list_names(sub)

list_names(co)

