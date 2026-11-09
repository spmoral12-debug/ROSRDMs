"""Start the packaged backend with strict lobby sessions and battle joins."""

import json
from pathlib import Path
import runpy
import sys

# The bundled Windows Python uses an isolated ._pth search path.
sys.path.insert(0, str(Path(__file__).resolve().parent))


def install_session_checks():
    from backend_server.auth import Accounts
    from backend_server.battle_server import JOIN_PREFIX, LocalBattleServer
    from backend_server.game_server import LocalGameServer
    from backend_server.sessions import SessionError, SessionManager

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

    def join(self, sock, peer, server, data):
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


if __name__ == "__main__":
    import profile_controls

    install_session_checks()
    runpy.run_module("backend_server", run_name="__main__", alter_sys=True)
