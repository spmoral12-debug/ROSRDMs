import dis

with open(r'C:\DieHardROS\runtime\app\start_game.pyc', 'rb') as f:
    header = f.read(16)
    import marshal
    code = marshal.load(f)

print("Co_names:", code.co_names)
print("Co_consts:", [c for c in code.co_consts if not hasattr(c, 'co_code')])

