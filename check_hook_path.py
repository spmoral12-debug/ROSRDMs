import sys, os
sys.path.insert(0, r"C:\DieHardROS\runtime\app")
os.environ['ROS_RT_KEY'] = 'f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf'

import rrboot
rrboot.install()

import client.inject_lobby as inj
print(">>> HOOK_PATH:", inj.HOOK_PATH)
print(">>> BATTLE_HOOK_PATH:", inj.BATTLE_HOOK_PATH)
