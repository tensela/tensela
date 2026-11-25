"""How the window of Tensela starts: one window for all.

If Tensela is already open (for the same person and preferences), a second start does not open another window: it
hands its projects to the window that is open (a `.tela` opened with a double click arrives there as a new tab) and
ends. It is quick because it does not load the rest of Tensela to find out.

The open window listens on a local socket (`$XDG_RUNTIME_DIR/tensela-<key>.sock`, only for this person); the key
comes from the preferences folder, so a Tensela started with other preferences (a test) is a window of its own.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import tempfile
from pathlib import Path


def address() -> str:
    """Where the open window listens."""
    config = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    key = hashlib.sha1(f"{os.getuid()}:{Path(config).resolve()}".encode("utf-8")).hexdigest()[:12]
    path = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()) / f"tensela-{key}.sock"
    if len(str(path).encode("utf-8")) > 100:          # a local socket's address has room for about 100 characters
        path = Path(tempfile.gettempdir()) / f"tensela-{os.getuid()}-{key}.sock"
    return str(path)


def hand_over(files: list[str], timeout: float = 2.0) -> bool:
    """Gives `files` to the window that is open. False if there is none (then this start opens the window)."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(address())
            from .activate import tokens                 # the permission to come to the front (ui/activate.py)
            connection.sendall(json.dumps({"files": files, **tokens()}).encode("utf-8") + b"\n")
            try:
                connection.recv(16)                  # «ok»: it arrived (if it does not answer, it was sent anyway)
            except OSError:
                pass
            return True
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if args[:1] == ["--pack-extension"]:                # an extension being written, packed to share
        from .. import language
        from ..data import ShapeError
        from ..extensions import pack
        language.LANGUAGE = language.system_language()
        if len(args) < 2:
            print("tensela-app --pack-extension <folder> [<where to leave the .zip>]", file=sys.stderr)
            return 2
        try:
            target, fingerprint = pack(Path(args[1]), Path(args[2]) if len(args) > 2 else None)
        except (ShapeError, OSError) as error:
            print(str(error), file=sys.stderr)
            return 2
        print(target)
        print(f"sha256 {fingerprint}")
        return 0
    if args[:1] == ["--extension"]:                     # the command of an extension, without the window
        from .. import language
        from ..extensions import run_command
        language.LANGUAGE = language.system_language()
        return run_command(args[1] if len(args) > 1 else "", args[2:])
    # Only the projects are handed over; with options (development, a capture…) it is a window of its own.
    if not any(a.startswith("-") for a in args) and hand_over([str(Path(a).resolve()) for a in args]):
        return 0
    from .window import main as window
    return window(args)


if __name__ == "__main__":
    sys.exit(main())
