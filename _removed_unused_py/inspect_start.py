import marshal

with open(r"C:\DieHardROS\runtime\app\start_game.pyc", "rb") as f:
    f.seek(16)
    co = marshal.load(f)

print(">>> STRINGS SA START_GAME.PYC:")
for s in [c for c in co.co_consts if isinstance(c, str)]:
    if any(k in s.lower() for k in ["hook", "update", "lobby", "remote", ".py", "http"]):
        print("   ", s)
