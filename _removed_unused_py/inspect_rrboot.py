import marshal

with open(r"C:\DieHardROS\runtime\app\rrboot.pyc", "rb") as f:
    f.seek(16)
    co = marshal.load(f)

print(">>> STRINGS SA RRBOOT.PYC:")
for s in [c for c in co.co_consts if isinstance(c, str)]:
    if len(s.strip()) > 3:
        print("   ", s[:100].replace("\n", " "))
