"""Check and install a complete, checksum-verified set of player hot patches."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.request import Request, urlopen

REPOSITORY = "spmoral12-debug/ROSRDMs"
PATCHES = ("remote-lobby.py", "remote-battle.py")
FILES = tuple(name for patch in PATCHES for name in (patch, patch + ".sha256"))
ROOT = Path(__file__).resolve().parent
HOT = ROOT / "local_update" / "hot"


def fetch(url, limit):
    request = Request(url, headers={"User-Agent": "ROS-Redemption-Launcher",
                                    "Cache-Control": "no-cache"})
    with urlopen(request, timeout=12) as response:
        content = response.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Update file exceeds the size limit.")
    return content


def checksum(value):
    digest = value.decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Invalid patch checksum.")
    return digest


def valid(path, digest):
    if not path.is_file():
        return False
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() == digest


def update():
    metadata = json.loads(fetch(f"https://api.github.com/repos/{REPOSITORY}/commits/main", 500_000))
    revision = metadata["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Invalid update revision.")
    base = f"https://raw.githubusercontent.com/{REPOSITORY}/{revision}/local_update/hot"
    HOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".update-", dir=HOT) as temporary:
        stage = Path(temporary)
        changed = []
        for patch in PATCHES:
            sidecar = patch + ".sha256"
            digest = checksum(fetch(f"{base}/{sidecar}", 256))
            if valid(HOT / patch, digest):
                if (HOT / sidecar).is_file() and (HOT / sidecar).read_bytes().strip() == digest.encode("ascii"):
                    continue
                shutil.copyfile(HOT / patch, stage / patch)
            else:
                (stage / patch).write_bytes(fetch(f"{base}/{patch}", 32 * 1024 * 1024))
            if not valid(stage / patch, digest):
                raise ValueError(f"Checksum mismatch for {patch}.")
            (stage / sidecar).write_text(digest, encoding="ascii")
            changed.extend((patch, sidecar))

        backup = stage / "backup"
        backup.mkdir()
        for name in changed:
            if (HOT / name).is_file():
                shutil.copyfile(HOT / name, backup / name)
        installed = []
        try:
            for name in changed:
                os.replace(stage / name, HOT / name)
                installed.append(name)
        except OSError:
            for name in reversed(installed):
                if (backup / name).is_file():
                    os.replace(backup / name, HOT / name)
                else:
                    (HOT / name).unlink()
            raise
    return bool(changed)


def installed_are_valid():
    try:
        return all(valid(HOT / name, checksum((HOT / (name + ".sha256")).read_bytes()))
                   for name in PATCHES)
    except (OSError, ValueError):
        return False


if __name__ == "__main__":
    try:
        print("Game patches updated." if update() else "Game patches are up to date.")
    except Exception as error:
        if not installed_are_valid():
            print("Update failed and installed patches could not be verified.", flush=True)
            raise SystemExit(1) from error
        print("Update check unavailable. Using verified installed patches.")
        raise SystemExit(2) from None
