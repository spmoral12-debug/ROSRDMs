#!/usr/bin/env python3
"""Issue or retrieve a launcher login token directly on the dedicated server."""

import argparse
from pathlib import Path
import sys

# Ensure backend_server is in search path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend_server.auth import Accounts
from backend_server.database import Database
from backend_server.paths import ACCOUNTS_DB_PATH, SERVERS_PATH
from backend_server.servers import load_servers


def main():
    parser = argparse.ArgumentParser(description="Issue an authentication token for a player")
    parser.add_argument("username", help="Username of the player")
    parser.add_argument("--password", default="Redemption123!", help="Password to set if account needs registration")
    args = parser.parse_args()

    db = Database(ACCOUNTS_DB_PATH)
    accounts = Accounts(db)
    servers = load_servers(SERVERS_PATH)
    server = servers[0] if servers else None
    public_host = server.host if server else "143.14.88.9"
    lobby_port = server.port if server else 30061

    # Check if account exists
    account = db.account(args.username)
    if account is None:
        try:
            res = accounts.register(args.username, f"{args.username}@ros.redemption", args.password)
            token = res["token"]
            account_id = res["account_id"]
            print(f"[+] Registered new account '{args.username}'")
        except Exception as e:
            sys.exit(f"[-] Failed to register account: {e}")
    else:
        account_id = account["id"]
        # Try sign in, or set password if missing auth
        try:
            res = accounts.sign_in(args.username, args.password)
            token = res["token"]
        except Exception:
            # Generate a session directly in login_tokens
            import secrets, time
            token = secrets.token_urlsafe(32)
            now = int(time.time())
            expires = now + 30 * 86400
            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO login_tokens (token, account_id, created, expires) VALUES (?, ?, ?, ?)",
                    (token, account_id, now, expires)
                )
            print(f"[+] Issued token directly for existing account '{args.username}'")

    print(f"\n=======================================================")
    print(f" Account ID : {account_id}")
    print(f" Username   : {args.username}")
    print(f" Token      : {token}")
    print(f" Server Host: {public_host}:{lobby_port}")
    print(f"=======================================================")
    print("\nClient command to launch directly:")
    print(f'python start_diehard_local.py --direct --remote-servers online_servers.json --account {args.username} --token {token} --account-id {account_id}\n')


if __name__ == "__main__":
    main()
