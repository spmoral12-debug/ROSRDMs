import dis, marshal, types

with open(r"C:\DieHardROS\ROS_Redemption_Server_Package\backend_server\features\supplement.pyc", "rb") as f:
    co = marshal.loads(f.read()[16:])

def dump_action_open(c):
    for sub in c.co_consts:
        if isinstance(sub, types.CodeType):
            if sub.co_name == "action_open":
                for inst in dis.get_instructions(sub):
                    if inst.starts_line and inst.starts_line >= 530 and inst.starts_line <= 555:
                        print(f"L{inst.starts_line}: {inst.opname} {inst.argval}")
                    elif not inst.starts_line and getattr(inst, 'line_number', 0) >= 530 and getattr(inst, 'line_number', 0) <= 555:
                        pass
                return
            dump_action_open(sub)

dump_action_open(co)

