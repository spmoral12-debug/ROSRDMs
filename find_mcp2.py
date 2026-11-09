import marshal, types, dis

with open(r"C:\DieHardROS\ROS_Redemption_Server_Package\backend_server\chat.pyc", "rb") as f:
    co = marshal.loads(f.read()[16:])

instructions = list(dis.get_instructions(co))
for i, inst in enumerate(instructions):
    if inst.opname == "STORE_NAME" and inst.argval == "MAIL_CURRENCY_PROPS":
        for j in range(max(0, i-15), i+1):
            print(instructions[j].opname, instructions[j].argval)

