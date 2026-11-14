"""Connect to ROS Redemption VPS Dedicated Server over the Internet."""
import argparse
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

DEFAULT_API_URL = "http://143.14.88.9:30063"


def http_post(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "ROS-Redemption-Client/1.0"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        try:
            err_json = json.loads(err.read().decode("utf-8"))
            msg = err_json.get("message") or err_json.get("error")
        except Exception:
            msg = str(err)
        return {"ok": False, "error": msg, "message": msg}


def http_get(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ROS-Redemption-Client/1.0"},
        method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        try:
            err_json = json.loads(err.read().decode("utf-8"))
            msg = err_json.get("message") or err_json.get("error")
        except Exception:
            msg = str(err)
        return {"ok": False, "error": msg, "message": msg}


def prepare_online_identity(root, username, account_id):
    path = root / "local_update" / "local_identity.json"
    if path.is_file():
        return
    identity = {
        "aid": str(100000000 + int(account_id or 0)),
        "sdkuid": username,
        "gas_token": "local-offline-token",
        "username": username,
        "chl_sdk_json": "{}",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".local-identity-", delete=False) as file:
            temporary = Path(file.name)
            json.dump(identity, file)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Connect to ROS Redemption VPS")
    parser.add_argument("--api", default=DEFAULT_API_URL, help="VPS API URL (default: %(default)s)")
    parser.add_argument("--username", "-u", help="Username")
    parser.add_argument("--password", "-p", help="Password")
    parser.add_argument("--register", action="store_true", help="Register a new account")
    parser.add_argument("--launcher-input", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    supplied_password = sys.stdin.readline().rstrip("\r\n") if args.launcher_input else args.password

    root = Path(__file__).resolve().parent
    config_file = root / ".online_session.json"
    session_data = {}
    if config_file.is_file():
        try:
            session_data = json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    username = args.username or (session_data.get("username") if not args.register else None)
    if not username and args.launcher_input:
        sys.exit("[-] Sign in with your ROS Redemption username and password.")
    if not username:
        print("=== ROS Redemption Online Login ===")
        username = input("Username: ").strip()

    if not username:
        sys.exit("Username cannot be empty.")

    token = None
    account_id = None

    # Check health and fetch remote servers
    print(f"Connecting to VPS at {args.api}...")
    try:
        health = http_get(f"{args.api}/api/health")
        if not health.get("ok"):
            print("Warning: VPS API health check returned non-ok.")
    except Exception as e:
        sys.exit(f"Failed to reach VPS API at {args.api}: {e}\nMake sure the server is running on the VPS.")

    servers_resp = http_get(f"{args.api}/api/servers")
    servers_list = servers_resp.get("servers", [])
    if not servers_list:
        sys.exit("No servers returned from VPS API.")

    remote_servers_path = root / "online_servers.json"
    remote_servers_path.write_text(json.dumps({"servers": servers_list}, indent=2), encoding="utf-8")
    print(f"Retrieved {len(servers_list)} server(s): {', '.join(s.get('name', 'Server') for s in servers_list)}")

    # Update local server list so the game UI selects Singapore-Dedicated
    try:
        sys.path.insert(0, str(root / "ROS_Redemption_Server_Package"))
        from backend_server.servers import GameServer, server_list_text
        g_servers = [
            GameServer(
                id=int(s.get("id", 10501)),
                name=str(s.get("name", "Singapore-Dedicated")),
                port=int(s.get("port", 30061)),
                host=str(s.get("host", "143.14.88.9"))
            ) for s in servers_list
        ]
        sl_text = server_list_text(g_servers)
        (root / "local_update" / "server_list_pc.txt").write_text(sl_text + "\n", encoding="utf-8")
        extracted_lu = root / "server_extracted" / "local_update"
        if extracted_lu.is_dir():
            (extracted_lu / "server_list_pc.txt").write_text(sl_text + "\n", encoding="utf-8")
    except Exception:
        pass

    # Check if we have a saved valid token
    if session_data.get("username") == username and session_data.get("token") and not supplied_password and not args.register:
        token = session_data.get("token")
        account_id = session_data.get("account_id")
        print(f"Using saved session for {username}.")

    if not token:
        password = supplied_password
        if not password and args.launcher_input:
            sys.exit("[-] Sign in with your ROS Redemption username and password.")
        if not password:
            password = getpass.getpass("Password (minimum 8 characters): ")

        if args.register:
            if len(password) < 8:
                sys.exit("Registration failed: Password must be at least 8 characters.")
            email = input("Email (optional, press Enter to use default): ").strip()
            if not email:
                email = f"{username}@game.net"
            print(f"Registering account '{username}'...")
            res = http_post(f"{args.api}/api/register", {
                "username": username,
                "email": email,
                "password": password
            })
        else:
            print(f"Logging in as '{username}'...")
            res = http_post(f"{args.api}/api/login", {
                "identity": username,
                "password": password
            })

        if not res.get("ok"):
            err_msg = res.get("message") or res.get("error") or "Authentication failed"
            sys.exit(f"[-] {err_msg}")

        token = res.get("token")
        account_id = res.get("account_id")
        config_file.write_text(json.dumps({
            "username": username,
            "account_id": account_id,
            "token": token
        }, indent=2), encoding="utf-8")
        print("Login successful! Session saved.")

    # The packaged game needs a local UniSDK bootstrap identity. Lobby login
    # separately uses the signed session returned by the online server.
    prepare_online_identity(root, username, account_id)

    # Launch the game with start_diehard_local.py
    python_exe = root / "runtime" / "python" / "python.exe"
    if not python_exe.is_file():
        python_exe = root / "ROS_Redemption_Server_Package" / "python" / "python.exe"

    cmd = [
        str(python_exe),
        "-u",
        str(root / "start_diehard_local.py"),
        "--direct",
        "--remote-servers",
        str(remote_servers_path),
        "--account",
        username,
        "--token",
        token,
        "--account-id",
        str(account_id or 0)
    ]

    env = dict(os.environ)
    env["ROS_GAME_DIR"] = str(root)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    print("\nStarting ROS Redemption Online client...")
    sys.exit(subprocess.call(cmd, env=env, cwd=str(root)))


if __name__ == "__main__":
    main()
