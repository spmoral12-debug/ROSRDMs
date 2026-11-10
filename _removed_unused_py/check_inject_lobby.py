import sys, os, marshal
sys.path.insert(0, r"C:\DieHardROS\runtime\app")
os.environ['ROS_RT_KEY'] = 'f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf'

import rrboot
rrboot.install()

bundle = getattr(rrboot, '_bundle', None) or rrboot
raw = bundle.read('client/inject_lobby.pyc')
if raw:
    co = marshal.loads(raw[16:])
    print(">>> STRINGS SA INJECT_LOBBY.PYC:")
    for s in [c for c in co.co_consts if isinstance(c, str)]:
        print("   ", s.replace("\n", " ")[:120])
else:
    print("Cannot read inject_lobby.pyc")
