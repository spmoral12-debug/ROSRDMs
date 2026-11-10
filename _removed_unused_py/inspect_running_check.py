import marshal
import dis

with open(r"c:\Users\seanj\dev\server_extracted\run_ros_local.pyc", "rb") as f:
    f.seek(16)
    code = marshal.load(f)

for const in code.co_consts:
    if hasattr(const, 'co_consts'):
        for c in const.co_consts:
            if isinstance(c, str) and 'already running' in c:
                print("FOUND IN INNER CODE:", const.co_name)
                dis.dis(const)
                break
    elif isinstance(const, str) and 'already running' in const:
        print("FOUND IN MAIN CODE:")
        dis.dis(code)
        break

