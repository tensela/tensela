"""Signs the fingerprints of a release with minisign, so anyone can check that Tensela published them.

The fingerprints (SHA256SUMS) say a file arrived whole; the signature says who wrote the fingerprints. It is made with
a secret key that only whoever publishes Tensela has, kept off the work computer (on a removable drive, with a copy
somewhere safe). The public key, `tensela.pub`, goes in the repository and on the Download page.

    tools/sign_release.py new-key /media/<you>/<drive>/tensela.key   # once: the pair of keys
    tools/sign_release.py sign /media/<you>/<drive>/tensela.key      # each release: signs build/appimage/SHA256SUMS
    tools/sign_release.py check                                      # checks the signature with tensela.pub

minisign asks for the password of the key itself: run it in your own terminal. `sudo apt install minisign` if it is
missing. What to upload with each release: SHA256SUMS and SHA256SUMS.minisig, beside the AppImage and the .tar.gz.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "appimage"
SUMS = BUILD / "SHA256SUMS"
PUBLIC = ROOT / "tensela.pub"
SITE_REPO = Path(os.environ.get("TENSELA_SITE") or ROOT.parent / "tensela-site")
#: Folders a secret key must never be written in: they are, or will be, published.
PUBLISHED = [ROOT, ROOT.parent / "tensela", SITE_REPO]


def say(text: str) -> None:
    print(f"==> {text}", flush=True)


def minisign() -> str:
    found = shutil.which("minisign")
    if not found:
        sys.exit("minisign is not installed: sudo apt install minisign")
    return found


def outside_repositories(key: Path) -> Path:
    key = key.expanduser().resolve()
    for folder in PUBLISHED:
        if key.is_relative_to(folder.resolve()):
            sys.exit(f"The secret key cannot go in {folder}: that folder is published. Use a removable drive.")
    return key


def public_key() -> str:
    """The key itself: the second line of tensela.pub (the first is a comment)."""
    lines = [line.strip() for line in PUBLIC.read_text(encoding="utf-8").splitlines() if line.strip()]
    return lines[-1]


def to_site() -> None:
    """The public key on the Download page (src/data/signing.json of the site, when it is beside)."""
    data = SITE_REPO / "src" / "data"
    if data.is_dir():
        (data / "signing.json").write_text(json.dumps({"minisign": public_key()}, indent=2) + "\n", encoding="utf-8")
        say("The public key is also on the Download page of the site")


def new_key(key: Path) -> int:
    key = outside_repositories(key)
    if PUBLIC.exists():
        sys.exit(f"{PUBLIC.name} already exists: a new key would make the old signatures impossible to check. "
                 "Move it aside first if that is what you want.")
    key.parent.mkdir(parents=True, exist_ok=True)
    say("minisign asks for a password twice: a long one, kept in your password manager")
    done = subprocess.run([minisign(), "-G", "-p", str(PUBLIC), "-s", str(key)])
    if done.returncode:
        return done.returncode
    say(f"Secret key: {key} (make a copy of it somewhere safe, off this computer)")
    say(f"Public key: {PUBLIC.name}, {public_key()}")
    to_site()
    return 0


def sign(key: Path) -> int:
    key = outside_repositories(key)
    if not SUMS.exists():
        sys.exit(f"There is no {SUMS.relative_to(ROOT)}: build the AppImage first (tools/build_appimage.py).")
    version = json.loads((BUILD / "release.json").read_text(encoding="utf-8"))["version"]
    say(f"Signing the fingerprints of Tensela {version}: minisign asks for the password of the key")
    done = subprocess.run([minisign(), "-S", "-s", str(key), "-m", str(SUMS), "-t", f"Tensela {version}"])
    if done.returncode:
        return done.returncode
    return check()


def check() -> int:
    if not PUBLIC.exists():
        sys.exit(f"There is no {PUBLIC.name}: make the keys first (new-key).")
    done = subprocess.run([minisign(), "-V", "-p", str(PUBLIC), "-m", str(SUMS)])
    if done.returncode == 0:
        say(f"Upload with the release: {SUMS.name} and {SUMS.name}.minisig")
    return done.returncode


def main(args: list[str]) -> int:
    if args[:1] == ["new-key"] and len(args) == 2:
        return new_key(Path(args[1]))
    if args[:1] == ["sign"] and len(args) == 2:
        return sign(Path(args[1]))
    if args == ["check"]:
        return check()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
