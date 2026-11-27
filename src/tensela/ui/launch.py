"""How the window of Tensela starts: one window for all.

If Tensela is already open (for the same person and preferences), a second start does not open another window: it
hands its projects to the window that is open (a `.tela` opened with a double click arrives there as a new tab) and
ends. It is quick because it does not load the rest of Tensela to find out.

The open window listens on a local socket (`$XDG_RUNTIME_DIR/tensela-<key>.sock`, or `/tmp/tensela-<uid>/…` made only
for this person when the session has no folder of its own); on Windows, on a named pipe (`tensela-<key>` among the pipes
of the computer, open only to this person). The key comes from the preferences folder, so a Tensela started with other preferences (a
test) is a window of its own.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
import sys
import tempfile
import threading
from pathlib import Path

WINDOWS = os.name == "nt"


def _person() -> str:
    """Who is using the computer: the user number on Linux, the user name on Windows (it has no numbers)."""
    return str(os.getuid()) if hasattr(os, "getuid") else os.environ.get("USERNAME", "")


def own_folder() -> Path | None:
    """A folder of this person in the temporary one (/tmp/tensela-<uid>), made only for them (mode 700), for when the
    session has no folder of its own ($XDG_RUNTIME_DIR: some minimal sessions, su, a remote shell). None if it exists
    and is not only theirs: someone else could have left a socket there to receive what Tensela hands over."""
    folder = Path(tempfile.gettempdir()) / f"tensela-{_person()}"
    try:
        folder.mkdir(mode=0o700)
    except FileExistsError:
        pass
    except OSError:
        return None
    try:
        found = os.lstat(folder)
    except OSError:
        return None
    if not stat.S_ISDIR(found.st_mode) or found.st_uid != os.getuid() or found.st_mode & 0o077:
        return None
    return folder


def address() -> str:
    """Where the open window listens: in the folder of the session, which only this person can open, or in a folder of
    their own (`own_folder`). Never loose in the shared temporary folder: if there is no folder of their own, an address
    nobody else knows (then a second start opens a window of its own, which is safe). On Windows, the name of a pipe
    (the window's QLocalServer puts it among the pipes of the computer and opens it only to this person)."""
    config = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    key = hashlib.sha1(f"{_person()}:{Path(config).resolve()}".encode("utf-8")).hexdigest()[:12]
    if WINDOWS:
        return f"tensela-{key}"
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    for folder in ((Path(runtime),) if runtime and Path(runtime).is_dir() else ()) + (own_folder(),):
        if folder is not None:
            path = folder / f"tensela-{key}.sock"
            if len(str(path).encode("utf-8")) <= 100:   # a local socket's address has room for about 100 characters
                return str(path)
    global _NOBODY_KNOWS
    if _NOBODY_KNOWS is None:                          # the same one all along this process
        _NOBODY_KNOWS = Path(tempfile.mkdtemp(prefix="tensela-"))
    return str(_NOBODY_KNOWS / f"tensela-{key}.sock")


_NOBODY_KNOWS: Path | None = None


def _message(files: list[str]) -> bytes:
    from .activate import tokens                         # the permission to come to the front (ui/activate.py)
    return json.dumps({"files": files, **tokens()}).encode("utf-8") + b"\n"


def _hand_over_by_pipe(files: list[str], timeout: float) -> bool:
    """(Windows.) The same through the window's named pipe: it is opened as a file."""
    try:
        pipe = open(rf"\\.\pipe\{address()}", "r+b", buffering=0)
    except OSError:                                      # no window listening (or all its pipes busy)
        return False
    try:
        pipe.write(_message(files))
    except OSError:
        pipe.close()
        return False
    reader = threading.Thread(target=lambda: pipe.read(16), daemon=True)   # «ok»; a pipe has no timeout
    reader.start()
    reader.join(timeout)
    if not reader.is_alive():                            # (closing it while a read waits could wait too)
        pipe.close()
    return True


def hand_over(files: list[str], timeout: float = 2.0) -> bool:
    """Gives `files` to the window that is open. False if there is none (then this start opens the window)."""
    if WINDOWS:
        return _hand_over_by_pipe(files, timeout)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(timeout)
            connection.connect(address())
            connection.sendall(_message(files))
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
