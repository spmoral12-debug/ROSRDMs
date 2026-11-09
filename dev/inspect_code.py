import marshal
import dis

with open(r"c:\Users\seanj\dev\server_extracted\backend_server\battle_rpc.pyc", "rb") as f:
    f.seek(16)
    code = marshal.load(f)

print("CO_NAME:", code.co_name)
print("CONSTS:", [c for c in code.co_consts if not hasattr(c, 'co_name')][:20])
print("NAMES:", code.co_names)

dis.dis(code)

