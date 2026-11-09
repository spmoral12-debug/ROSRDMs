"""Local playtest entry point with branding for the pre-lobby patch screen."""
import os
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parent
# The running game holds ui.npk open on Windows. Install staged art before
# the next client process opens it.
staged_archive = root / "res" / "ui.redemption.next.npk"
if staged_archive.is_file() and not any(
    arg in ("-h", "--help", "--server-only") for arg in sys.argv[1:]
):
    try:
        os.replace(staged_archive, staged_archive.with_name("ui.npk"))
    except PermissionError:
        sys.exit("Close the running Rules of Survival game, then reopen this launcher.")
    print("Installed ROS Redemption loading artwork.", flush=True)

sys.path.insert(0, str(root / "server_extracted"))

sys.path.append(str(root / "ROS_Redemption_Server_Package"))

import profile_controls
from client import inject_lobby

read_source = inject_lobby.read_source
startup_source = (root / "startup_branding_hook.py").read_text(encoding="utf-8")


profile_source = (root / "profile_controls_hook.py").read_text(encoding="utf-8")
welfare_source = (root / "welfare_lobby_hook.py").read_text(encoding="utf-8")


def read_with_startup_branding(path):
    source = read_source(path)
    if Path(path) == inject_lobby.HOOK_PATH:
        return "\n\n".join((source, startup_source, profile_source, welfare_source))
    return source


inject_lobby.read_source = read_with_startup_branding
runpy.run_module("run_ros_local", run_name="__main__")
