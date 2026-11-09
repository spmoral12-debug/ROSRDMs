import marshal
import dis

with open(r"c:\Users\seanj\dev\server_extracted\backend_server\battle_rpc.pyc", "rb") as f:
    f.seek(16)
    code = marshal.load(f)

for const in code.co_consts:
    if hasattr(const, 'co_name') and const.co_name == 'ticket':
        print("TICKET DISASSEMBLY:")
        dis.dis(const)
        print("CONSTS:", const.co_consts)
        print("NAMES:", const.co_names)

