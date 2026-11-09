"""Local playtest entry point with branding for the pre-lobby patch screen."""
import os
from pathlib import Path
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

# Frida in-process window title interceptor
import run_ros_local
orig_agent_source = run_ros_local.persistent_agent_source

FRIDA_TITLE_INTERCEPTOR = r"""
(function() {
  try {
    const targetTitle = 'ROS REDEMPTION';
    const targetTitleW = Memory.allocUtf16String(targetTitle);
    const targetTitleA = Memory.allocUtf8String(targetTitle);

    const user32 = Process.getModuleByName('user32.dll');
    const setWindowTextW = user32.getExportByName('SetWindowTextW');
    const setWindowTextA = user32.getExportByName('SetWindowTextA');
    const createWindowExW = user32.getExportByName('CreateWindowExW');
    const createWindowExA = user32.getExportByName('CreateWindowExA');

    function isRosTitle(str) {
      if (!str) return false;
      return str.indexOf('Rules of Survival') !== -1 ||
             str.indexOf('DieHard') !== -1 ||
             str.indexOf('1.610660') !== -1 ||
             (str.indexOf('ROS') !== -1 && str !== targetTitle);
    }

    if (setWindowTextW) {
      Interceptor.attach(setWindowTextW, {
        onEnter(args) {
          try {
            if (!args[1].isNull()) {
              const s = args[1].readUtf16String();
              if (isRosTitle(s)) {
                args[1] = targetTitleW;
              }
            }
          } catch (_) {}
        }
      });
    }

    if (setWindowTextA) {
      Interceptor.attach(setWindowTextA, {
        onEnter(args) {
          try {
            if (!args[1].isNull()) {
              const s = args[1].readUtf8String();
              if (isRosTitle(s)) {
                args[1] = targetTitleA;
              }
            }
          } catch (_) {}
        }
      });
    }

    if (createWindowExW) {
      Interceptor.attach(createWindowExW, {
        onEnter(args) {
          try {
            if (!args[2].isNull()) {
              const s = args[2].readUtf16String();
              if (isRosTitle(s)) {
                args[2] = targetTitleW;
              }
            }
          } catch (_) {}
        }
      });
    }

    if (createWindowExA) {
      Interceptor.attach(createWindowExA, {
        onEnter(args) {
          try {
            if (!args[2].isNull()) {
              const s = args[2].readUtf8String();
              if (isRosTitle(s)) {
                args[2] = targetTitleA;
              }
            }
          } catch (_) {}
        }
      });
    }

    const enumWindows = new NativeFunction(user32.getExportByName('EnumWindows'), 'int', ['pointer', 'pointer']);
    const getWindowThreadProcessId = new NativeFunction(user32.getExportByName('GetWindowThreadProcessId'), 'uint32', ['pointer', 'pointer']);
    const isWindowVisible = new NativeFunction(user32.getExportByName('IsWindowVisible'), 'int', ['pointer']);
    const getWindowTextW = new NativeFunction(user32.getExportByName('GetWindowTextW'), 'int', ['pointer', 'pointer', 'int']);
    const doSetWindowTextW = new NativeFunction(setWindowTextW, 'int', ['pointer', 'pointer']);

    const textBuf = Memory.alloc(512);
    const pidBuf = Memory.alloc(4);
    const selfPid = Process.id;

    function scanWindows() {
      try {
        const cb = new NativeCallback(function(hwnd, lParam) {
          try {
            getWindowThreadProcessId(hwnd, pidBuf);
            if (pidBuf.readU32() === selfPid && isWindowVisible(hwnd)) {
              getWindowTextW(hwnd, textBuf, 256);
              const cur = textBuf.readUtf16String();
              if (cur && isRosTitle(cur)) {
                doSetWindowTextW(hwnd, targetTitleW);
              }
            }
          } catch (_) {}
          return 1;
        }, 'int', ['pointer', 'pointer']);
        enumWindows(cb, ptr(0));
      } catch (_) {}
    }

    setInterval(scanWindows, 200);
    scanWindows();
  } catch (err) {
    send({event: 'ros-redemption-title-hook-error', error: String(err)});
  }
})();
"""


def patched_agent_source(identity, encoded):
    base_src = orig_agent_source(identity, encoded)
    return base_src + "\n\n" + FRIDA_TITLE_INTERCEPTOR


run_ros_local.persistent_agent_source = patched_agent_source

if __name__ == "__main__":
    sys.exit(run_ros_local.main())
