import marshal, types, dis

with open(r"C:\DieHardROS\ROS_Redemption_Server_Package\backend_server\chat.pyc", "rb") as f:
    co = marshal.loads(f.read()[16:])

for inst in dis.get_instructions(co):
    if "MAIL_CURRENCY_PROPS" in str(inst.argval):
        print(inst.opname, inst.argval)

