"""Start the packaged backend with strict lobby sessions and battle joins."""

import json
import os
from pathlib import Path
import runpy
import sys
import threading

# The bundled Windows Python uses an isolated ._pth search path.
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))


def strip_packet_mac(data):
    """Strip the online client's '\\nDH1 <session> <seq> <mac>' trailer if present."""
    if isinstance(data, bytes) and b"\nDH1 " in data:
        return data.split(b"\nDH1 ", 1)[0]
    if isinstance(data, str) and "\nDH1 " in data:
        return data.split("\nDH1 ", 1)[0]
    return data


def start_auth_api(db, host="0.0.0.0", port=30063):
    """Serve launcher auth and server-list endpoints on a forwarded port."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from backend_server.auth import Accounts
    from backend_server.paths import SERVERS_PATH
    from backend_server.servers import load_servers

    accounts = Accounts(db)

    class AuthHandler(BaseHTTPRequestHandler):
        server_version = "ROS-Redemption-API/1.0"

        def log_message(self, format, *args):
            print(f"[api] {self.address_string()} - {format % args}", flush=True)

        def _send(self, code, obj):
            data = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ("/api/health", "/api/stats"):
                online_count = 0
                try:
                    import time
                    now = int(time.time())
                    c = db.cursor()
                    c.execute("SELECT count(DISTINCT account_id) FROM login_tokens WHERE expires > ?", (now,))
                    row = c.fetchone()
                    online_count = int(row[0]) if row and row[0] is not None else 0
                    if online_count < 1:
                        c.execute("SELECT count(*) FROM characters WHERE last_login > ?", (now - 3600,))
                        row2 = c.fetchone()
                        online_count = int(row2[0]) if row2 and row2[0] is not None else 0
                except Exception:
                    online_count = 1

                patch_notes = [
                    "✅ [LAUNCHER] Official Standalone Client (No .bat, Real-Time Stats)",
                    "✅ [FIXED] Team Leave Instant Unform & Member Sync",
                    "✅ [FIXED] 3D Lobby Road & Mountain Sky Elevation (Theme 279008)",
                    "✅ [VEHICLE] Car Skin Auto-Equip on Boarding",
                    "✅ [VEHICLE] Nitro Turbo Boost (Shift Key & Flames)",
                    "✅ [VEHICLE] Fuel Consumption & Smooth Engine Audio",
                    "✅ [COMBAT] Safe Fall Damage (High Cliffs only)",
                    "✅ [STORE] Pack Buy Again & Universal Guaranteed Pity System",
                    "✅ [BALANCE] 125 Spawn Point Spread on Prepare Island"
                ]

                return self._send(200, {
                    "ok": True,
                    "status": "online",
                    "server": "Singapore-Dedicated",
                    "host": "143.14.88.9",
                    "players_online": max(1, online_count),
                    "version": "1.2.0",
                    "patch_notes": patch_notes
                })
            if self.path == "/api/patch_notes":
                return self._send(200, {
                    "ok": True,
                    "version": "1.2.0",
                    "patch_notes": [
                        "✅ [LAUNCHER] Official Standalone Client (No .bat, Real-Time Stats)",
                        "✅ [FIXED] Team Leave Instant Unform & Member Sync",
                        "✅ [FIXED] 3D Lobby Road & Mountain Sky Elevation (Theme 279008)",
                        "✅ [VEHICLE] Car Skin Auto-Equip on Boarding",
                        "✅ [VEHICLE] Nitro Turbo Boost (Shift Key & Flames)",
                        "✅ [VEHICLE] Fuel Consumption & Smooth Engine Audio",
                        "✅ [COMBAT] Safe Fall Damage (High Cliffs only)",
                        "✅ [STORE] Pack Buy Again & Universal Guaranteed Pity System",
                        "✅ [BALANCE] 125 Spawn Point Spread on Prepare Island"
                    ]
                })
            if self.path == "/api/servers":
                try:
                    servers = load_servers(SERVERS_PATH)
                    res = [{"id": s.id, "name": s.name, "port": s.port, "host": s.host, "zone": s.zone} for s in servers]
                    return self._send(200, {"ok": True, "servers": res})
                except Exception as e:
                    return self._send(500, {"ok": False, "error": str(e)})
            return self._send(404, {"ok": False, "error": "not_found"})

        def do_POST(self):
            size = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(size).decode("utf-8")) if size > 0 else {}
            except Exception:
                return self._send(400, {"ok": False, "error": "bad_json"})

            if self.path == "/api/login":
                identity = str(body.get("identity") or body.get("username") or "").strip()
                password = str(body.get("password") or "").strip()
                try:
                    res = accounts.sign_in(identity, password)
                    return self._send(200, res)
                except Exception as e:
                    return self._send(401, {"ok": False, "error": "bad_login", "message": str(e)})

            if self.path == "/api/register":
                username = str(body.get("username") or "").strip()
                email = str(body.get("email") or f"{username}@ros.redemption").strip()
                password = str(body.get("password") or "").strip()
                try:
                    res = accounts.register(username, email, password)
                    return self._send(200, res)
                except Exception as e:
                    return self._send(400, {"ok": False, "error": "register_failed", "message": str(e)})

            return self._send(404, {"ok": False, "error": "not_found"})

    try:
        httpd = HTTPServer((host, port), AuthHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        print(f"[api] Auth & Server-list service listening on http://{host}:{port}", flush=True)
    except Exception as e:
        print(f"[api] Warning: could not start API server on {host}:{port}: {e}", flush=True)


def install_session_checks():
    from backend_server.auth import Accounts
    from backend_server.battle_server import JOIN_PREFIX, LocalBattleServer
    import backend_server.battle_server as bs
    import backend_server.chunks as chunks
    import backend_server.game_server as gs
    from backend_server.game_server import LocalGameServer
    from backend_server.pyserver import rpc
    from backend_server.sessions import SessionError, SessionManager

    # Map battle port to lobby port + 1 (e.g. 30061 + 1 = 30062)
    bs.BATTLE_PORT_OFFSET = int(os.environ.get("BATTLE_PORT_OFFSET", 1))

    # Strip online client DH1 packet signatures before JSON parsing
    orig_unpack_request = chunks.unpack_request
    orig_json_after = gs._json_after
    orig_battle_dispatch = LocalBattleServer._dispatch

    def clean_unpack_request(data):
        res = orig_unpack_request(strip_packet_mac(data))
        return strip_packet_mac(res) if res is not None else None

    def clean_json_after(data, prefix):
        return orig_json_after(strip_packet_mac(data), prefix)

    def clean_battle_dispatch(self, sock, peer, server, data):
        return orig_battle_dispatch(self, sock, peer, server, strip_packet_mac(data))

    chunks.unpack_request = clean_unpack_request
    gs._json_after = clean_json_after
    LocalBattleServer._dispatch = clean_battle_dispatch

    @rpc("dhGuardReport")
    def handle_guard_report(server, args, kwargs):
        return {"ok": True, "callbacks": []}

    login = SessionManager.login
    get = SessionManager.get
    game_start = LocalGameServer.start
    battle_join = LocalBattleServer._join
    managers = {}

    def authenticated_login(self, username, server, token=None):
        if not isinstance(token, str) or not token.strip() or self.accounts is None:
            raise SessionError("bad_token", "Sign in through the launcher first.")
        return login(self, username, server, token)

    def explicit_session(self, token=None, server=None):
        if not isinstance(token, str) or not token.strip():
            return None
        session = get(self, token, server)
        if session is not None and server is not None and session.server.id != server.id:
            return None
        return session

    def start(self):
        game_start(self)
        if self.sessions.accounts is None:
            self.sessions.accounts = Accounts(self.db)
        for server in self.listening:
            managers[server.id] = self.sessions
        api_port = int(os.environ.get("API_PORT", 30063))
        start_auth_api(self.db, host="0.0.0.0", port=api_port)
        try:
            import backend_server.admin as admin_mod
            admin_port = int(os.environ.get("ADMIN_PORT", 8790))
            admin_key = admin_mod.local_key(admin_mod.LOCAL_KEY_PATH)
            admin_api = admin_mod.AdminApi(
                self.db,
                self.listening,
                admin_key,
                None,
                None,
                admin_mod.AUDIT_PATH,
                admin_mod.BATTLE_PATH,
                admin_mod.ITEMS_PATH,
                admin_mod.MATCH_SETTINGS_PATH,
            )
            admin_mod.local_server(admin_api, port=admin_port, host="127.0.0.1")
            print(f"[admin] Private Admin Panel listening on http://127.0.0.1:{admin_port}/admin", flush=True)
        except Exception as e:
            print(f"[admin] Warning starting admin server: {e}", flush=True)

    def join(self, sock, peer, server, data):
        data = strip_packet_mac(data)
        try:
            request = json.loads(data[len(JOIN_PREFIX):])
        except (ValueError, UnicodeError):
            request = {}
        if not isinstance(request, dict):
            request = {}
        manager = managers.get(server.id)
        session = manager.get(request.get("session"), server) if manager else None
        if session is None or request.get("gid") != session.gid:
            self._reply(sock, peer, {
                "ok": False,
                "error": "bad_session",
                "message": "Sign in again before joining a match.",
            })
            return
        return battle_join(self, sock, peer, server, data)

    SessionManager.login = authenticated_login
    SessionManager.get = explicit_session
    LocalGameServer.start = start
    LocalBattleServer._join = join


def load_server_hot_patch():
    patch_file = ROOT_DIR / "local_update" / "hot" / "server_patch.py"
    if not patch_file.is_file():
        return
    try:
        code = patch_file.read_text(encoding="utf-8")
        local_logs = str(ROOT_DIR / "local_update" / "logs")
        code = code.replace(
            "r'C:\\DieHardROS\\local_update\\logs',",
            f"{local_logs!r},\n        r'C:\\DieHardROS\\local_update\\logs',",
        )
        exec(compile(code, str(patch_file), "exec"), {"__name__": "__server_patch__", "__file__": str(patch_file)})
    except Exception as e:
        print(f"[server] Warning loading server_patch.py: {e}", flush=True)


if __name__ == "__main__":
    import profile_controls

    load_server_hot_patch()
    install_session_checks()
    runpy.run_module("backend_server", run_name="__main__", alter_sys=True)
