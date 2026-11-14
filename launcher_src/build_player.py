"""Build a player-only ROS Redemption folder from this workspace."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess

SOURCE = Path(__file__).resolve().parents[1]


def copy(source, destination):
    require_workspace_path(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def require_workspace_path(path):
    if not path.resolve(strict=True).is_relative_to(SOURCE):
        raise ValueError(f"Player package input is outside DieHardROS: {path}")


def copy_tree(source, target, skip=lambda name: False):
    require_workspace_path(source)

    def ignored(folder, names):
        excluded = []
        for name in names:
            if skip(name):
                excluded.append(name)
            else:
                require_workspace_path(Path(folder) / name)
        return excluded

    shutil.copytree(source, target, dirs_exist_ok=True, ignore=ignored)


def generated_or_private(name):
    lower = name.lower()
    return (lower.endswith((".log", ".jsonl", ".dmp", ".bak", ".orig", ".original", ".db",
                            ".db-wal", ".db-shm", ".key", ".npk.patched1", ".next.npk"))
            or lower.startswith(("ros64_dump", "dlc_pc_launcher.plist"))
            or lower in {"__pycache__", "logs", "log.txt", "cclib_log.txt", "local_identity.json",
                         "admin_key.txt", "user_info.txt", "launcher_log.txt", "patch_temp", "patching",
                         ".online_session.json", "ros64_extracted_all.txt", "ros_launcher.exe"}
            or lower.startswith(("chat_history", "chat_meta", "market_record_point")))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("Choose a new output folder.")
    game = output / "Game"
    ui = output / "launcher"
    ui.mkdir(parents=True)

    for name in ("x64", "res", "AllysdkOverseaRes", "cclive_bin", "ccmini", "runtime/python",
                 "server_extracted/backend_server", "server_extracted/client",
                 "Documents/assets", "Documents/dlc_clothes", "Documents/patched",
                 "Documents/res", "Documents/script", "Documents/voice_data", "Documents/x64"):
        copy_tree(SOURCE / name, game / name, generated_or_private)
    # Keep installed resource metadata. Let the game create each player's settings.
    for name in ("abconfig", "firstPackVersion", "neox.xml", "no_first_patch.txt",
                 "no_patch.txt", "NtUniSdkAxeso.dll", "NtUniSdkSteam.dll", "pc.txt"):
        copy(SOURCE / "Documents" / name, game / "Documents" / name)
    for name in ("run_ros_local.pyc", "second_client.pyc", "local_update/server_list_pc.txt",
                 "local_update/server_data/player_props.json",
                 "local_update/server_data/rpc_responses.json"):
        copy(SOURCE / "server_extracted" / name, game / "server_extracted" / name)
    for dll in SOURCE.glob("*.dll"):
        copy(dll, game / dll.name)
    for name in ("assets.npk", "script.npk", "allysdk_global.data", "netease_global.data",
                 "h45na.prot", "NEACSDK.cfg", "ntunisdk.cfg", "ntunisdk_config", "neox.xml",
                 "RegionSelectWnd.xml", "setting.ini", "no_first_patch.txt", "no_patch.txt",
                 "pc.txt", "region", "ros_redemption.ico", "ros.ico", "connect_online.py",
                 "start_diehard_local.py", "startup_branding_hook.py", "profile_controls_hook.py",
                 "welfare_lobby_hook.py", "runtime/app/client/lobby_hook.py"):
        copy(SOURCE / name, game / name)
    copy(SOURCE / "ROS_Redemption_Server_Package/profile_controls.py",
         game / "ROS_Redemption_Server_Package/profile_controls.py")
    copy(SOURCE / "launcher_src/player_update.py", game / "player_update.py")
    copy(SOURCE / "launcher/assets/bg.jpg", ui / "artwork.jpg")

    for name in ("res", "pl"):
        copy_tree(SOURCE / "local_update" / name, game / "local_update" / name, generated_or_private)
    for name in ("match_settings.json", "player_props.json", "supplement_args.json",
                 "supplement_boxes.json"):
        copy(SOURCE / "local_update/server_data" / name, game / "local_update/server_data" / name)
    for name in ("server_list_pc.txt", "servers.json"):
        copy(SOURCE / "local_update" / name, game / "local_update" / name)
    hot = game / "local_update/hot"
    hot.mkdir()
    for name in ("remote-battle.py", "remote-lobby.py"):
        data = SOURCE / "local_update/hot" / name
        digest = data.with_suffix(".py.sha256")
        require_workspace_path(data)
        require_workspace_path(digest)
        with data.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != digest.read_text().strip():
                raise ValueError(f"Invalid patch checksum: {data}")
        copy(data, hot / name)
        copy(digest, hot / digest.name)
    copy(SOURCE / "local_update/hot/lobby_patch.py", hot / "lobby_patch.py")

    # The bundled compatibility mirror requires a loopback certificate.
    # Generate a fresh pair for the build instead of copying the workspace key.
    cert = game / "local_update/cert"
    cert.mkdir()
    openssl = shutil.which("openssl") or r"C:\Program Files\Git\usr\bin\openssl.exe"
    subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650",
                    "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
                    "-keyout", str(cert / "ros-update-local.key"),
                    "-out", str(cert / "ros-update-local.crt")],
                   check=True, capture_output=True)
    compiler = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
    subprocess.run([str(compiler), "/nologo", "/target:winexe", "/r:System.Drawing.dll",
                    "/r:System.Windows.Forms.dll", "/codepage:65001",
                    "/resource:" + str(SOURCE / "connect_online.py") + ",connect_online.py",
                    "/win32icon:" + str(SOURCE / "ros_redemption.ico"),
                    "/out:" + str(output / "ROS Redemption.exe"),
                    str(SOURCE / "launcher_src/PlayerLauncher.cs")], check=True)
    print(output)


if __name__ == "__main__":
    main()
