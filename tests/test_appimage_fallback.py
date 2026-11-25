"""The libraries for systems that lack them (usr/lib/fallback of the AppImage): AppRun turns on a folder only when the
system does not have the library it is named after, and Tensela gives the programs it opens their own path back."""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import appimage_lock  # noqa: E402
import build_appimage as B  # noqa: E402

SRC = Path(__file__).resolve().parent.parent / "src"


def _apprun(tmp_path: Path, present: list[str]) -> dict:
    here = tmp_path / "Tensela.AppDir"
    for name in ("libpresent.so.0", "libabsent-x.so.1"):
        (here / "usr" / "lib" / "fallback" / name).mkdir(parents=True)
    (here / "usr" / "bin").mkdir(parents=True)
    python = here / "usr" / "bin" / "python3"
    python.write_text('#!/bin/sh\nprintf \'{"path": "%s", "host": "%s"}\' "$LD_LIBRARY_PATH" '
                      '"${TENSELA_HOST_LIBRARY_PATH-unset}"\n')
    python.chmod(0o755)
    apprun = here / "AppRun"
    apprun.write_text(B.APPRUN)
    apprun.chmod(0o755)
    tools = tmp_path / "tools"                         # an ldconfig that knows only the libraries of `present`
    tools.mkdir()
    lines = "".join(f"\\t{name} (libc6,x86-64) => /usr/lib/{name}\\n" for name in present)
    (tools / "ldconfig").write_text(f'#!/bin/sh\nprintf "{lines}"\n')
    (tools / "ldconfig").chmod(0o755)
    env = {"PATH": f"{tools}:/usr/bin:/bin", "LD_LIBRARY_PATH": "/opt/mine", "APPIMAGE": "x"}
    out = subprocess.run([str(apprun)], env=env, capture_output=True, text=True, check=True).stdout
    return json.loads(out), here / "usr" / "lib" / "fallback"


def test_apprun_turns_on_only_the_folders_of_missing_libraries(tmp_path):
    found, fallback = _apprun(tmp_path, ["libpresent.so.0"])
    assert found["path"] == f"{fallback / 'libabsent-x.so.1'}:/opt/mine"
    assert found["host"] == "/opt/mine"


def test_apprun_leaves_the_path_alone_when_nothing_is_missing(tmp_path):
    found, _ = _apprun(tmp_path, ["libpresent.so.0", "libabsent-x.so.1"])
    assert found == {"path": "/opt/mine", "host": "unset"}


def test_tensela_gives_the_programs_it_opens_their_own_path():
    code = ("import os, tensela; "
            "print(os.environ.get('LD_LIBRARY_PATH', '-'), 'TENSELA_HOST_LIBRARY_PATH' in os.environ)")
    for host, expected in (("/opt/mine", "/opt/mine False"), ("", "- False")):
        env = dict(os.environ, PYTHONPATH=str(SRC), LD_LIBRARY_PATH="/fallback", TENSELA_HOST_LIBRARY_PATH=host)
        out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
        assert out.stdout.strip() == expected


def test_every_fallback_library_is_pinned_and_named_after_one_of_its_files():
    downloads = appimage_lock.read()["downloads"]
    for folder, keys in B.FALLBACK_LIBRARIES.items():
        assert folder in {downloads[k]["soname"] for k in keys}
        for key in keys:
            pinned = downloads[key]
            assert pinned["url"].startswith("http://archive.ubuntu.com/ubuntu/pool/main/")
            assert len(pinned["sha256"]) == 64 and len(pinned["file_sha256"]) == 64
