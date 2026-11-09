import marshal

with open(r"C:\DieHardROS\runtime\app\rrboot.pyc", "rb") as f:
    f.seek(16)
    co = marshal.load(f)

for c in co.co_consts:
    if hasattr(c, "co_name"):
        print(f"Func: {c.co_name}, Consts: {[x for x in c.co_consts if isinstance(x, (str, bytes))][:6]}")

with open(r"C:\DieHardROS\runtime\app\code.rrx", "rb") as f:
    hdr = f.read(32)
    print("\ncode.rrx header:", hdr)
