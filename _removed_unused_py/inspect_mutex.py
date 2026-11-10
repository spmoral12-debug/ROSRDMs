import marshal
import dis

with open(r"c:\Users\seanj\dev\server_extracted\run_ros_local.pyc", "rb") as f:
    f.seek(16)
    code = marshal.load(f)

for const in code.co_consts:
    if hasattr(const, 'co_name') and const.co_name == 'acquire_runner_mutex':
        print("FOUND acquire_runner_mutex:")
        dis.dis(const)
        break

