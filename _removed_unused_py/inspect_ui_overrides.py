import sys, os, marshal
sys.path.insert(0, r"C:\DieHardROS\runtime\app")
os.environ['ROS_RT_KEY'] = 'f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf'

import rrboot
rrboot.install()

bundle = getattr(rrboot, '_bundle', None) or getattr(rrboot, 'bundle', None) or rrboot
raw_ui = bundle.read('client/ui_overrides.pyc')
if raw_ui:
    co = marshal.loads(raw_ui[16:])
    print(">>> STRINGS SA CLIENT/UI_OVERRIDES.PYC:")
    for s in [c for c in co.co_consts if isinstance(c, str)]:
        if len(s.strip()) > 3:
            print("   ", s[:100].replace("\n", " "))
