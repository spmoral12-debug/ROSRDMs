import marshal

with open(r"c:\Users\seanj\dev\server_extracted\run_ros_local.pyc", "rb") as f:
    f.seek(16)
    code = marshal.load(f)

print("CO_NAME:", code.co_name)
print("CONSTS:", [c for c in code.co_consts if isinstance(c, str)][:15])
print("NAMES:", code.co_names[:30])

