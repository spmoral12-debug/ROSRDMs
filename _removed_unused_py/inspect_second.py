import marshal
import dis

with open(r"C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app\start_second.pyc", "rb") as f:
    f.seek(16)
    code = marshal.load(f)

print("START_SECOND:")
dis.dis(code)

with open(r"c:\Users\seanj\dev\server_extracted\second_client.pyc", "rb") as f:
    f.seek(16)
    code2 = marshal.load(f)

print("\nSECOND_CLIENT:")
print("CONSTS:", [c for c in code2.co_consts if isinstance(c, str)])
print("NAMES:", code2.co_names)
dis.dis(code2)

