import sys, os
sys.path.insert(0, r"C:\DieHardROS\runtime\app")
os.environ['ROS_RT_KEY'] = 'f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf'

import rrboot
rrboot.install()

bundle = getattr(rrboot, '_bundle', None) or getattr(rrboot, 'bundle', None) or rrboot
files = getattr(bundle, '_files', None) or getattr(rrboot, '_files', None)

for k in files:
    if "inject" in k or "sealed" in k:
        print(f"Key: {repr(k)}")
        data = rrboot.read(k)
        print(f"  read length: {len(data) if data else None}")
