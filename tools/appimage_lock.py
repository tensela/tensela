"""The lock of the AppImage: exactly what goes into it, so that nothing changes without being seen.

`tools/appimage.lock.json` keeps:

- the two things downloaded to build it (the portable Python and appimagetool): where they come from and their
  SHA-256, checked before they are used;
- each library: its version, its wheel on PyPI (file name, SHA-256 and the day it was published) and a fingerprint of
  its files as installed (from the hashes its RECORD lists, each one checked against the file).

`tools/appimage-requirements.txt` is the same list for pip, with the hashes, to make the environment again with
`pip install --require-hashes --only-binary=:all: -r tools/appimage-requirements.txt`.

The rules it keeps:

- nothing is updated by itself: a new version enters only when someone updates it by hand, reads what changed and
  writes the lock again with --update;
- a version enters only some time after it was published (COOL_DOWN_DAYS): most poisoned releases are found and
  taken down within days; --update refuses younger versions unless --allow-young is given, and says which;
- the build (tools/build_appimage.py) stops if the environment is not the one of the lock, or if a file does not
  match its hash.

    .venv/bin/python tools/appimage_lock.py                   # checks the environment against the lock (offline)
    .venv/bin/python tools/appimage_lock.py --update          # writes the lock again (asks PyPI for the wheels)
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "tools" / "appimage.lock.json"
REQUIREMENTS = ROOT / "tools" / "appimage-requirements.txt"
COOL_DOWN_DAYS = 14
#: Files that pip writes when it installs (not part of the wheel): its launchers and its own notes.
WRITTEN_BY_PIP = {"INSTALLER", "REQUESTED", "direct_url.json", "RECORD"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def record_hash(text: str) -> str | None:
    """The hash of a RECORD line («sha256=<urlsafe base64>») as hexadecimal, or None if it has none."""
    kind, _, value = text.partition("=")
    if kind != "sha256" or not value:
        return None
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).hex()


def entries(dist) -> list[tuple[str, str]]:
    """The files of a distribution that came in its wheel, with the hash its RECORD gives each one."""
    out = []
    for line in (dist.read_text("RECORD") or "").splitlines():
        path, _, rest = line.partition(",")
        expected = record_hash(rest.partition(",")[0])
        if expected is None or path.startswith("..") or path.rsplit("/", 1)[-1] in WRITTEN_BY_PIP \
                or path.endswith(".pyc"):
            continue
        out.append((path, expected))
    return sorted(out)


def fingerprint(dist, verify: bool) -> tuple[str, list[str]]:
    """One hash for all the files of a distribution, and (when `verify`) the files that do not match their hash."""
    wrong = []
    lines = entries(dist)
    if verify:
        for path, expected in lines:
            source = Path(dist.locate_file(path))
            if not source.is_file() or sha256_file(source) != expected:
                wrong.append(path)
    text = "\n".join(f"{path} {value}" for path, value in lines)
    return hashlib.sha256(text.encode()).hexdigest(), wrong


def tags(dist) -> list[str]:
    return [line[4:].strip() for line in (dist.read_text("WHEEL") or "").splitlines() if line.startswith("Tag:")]


def current(verify: bool = False) -> tuple[dict, list[str]]:
    """The libraries of the AppImage as they are installed now, and the problems found."""
    sys.path.insert(0, str(ROOT / "tools"))
    from build_appimage import closure
    libraries, problems = {}, []
    for dist in sorted(closure(), key=lambda d: d.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        files, wrong = fingerprint(dist, verify)
        problems += [f"{name}: {path} does not match its hash" for path in wrong]
        libraries[name] = {"version": dist.version, "tags": tags(dist), "files": files}
    return libraries, problems


def read() -> dict:
    return json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.is_file() else {"downloads": {}, "libraries": {}}


def differences(libraries: dict, lock: dict) -> list[str]:
    """What is different between the environment and the lock."""
    locked = lock.get("libraries", {})
    out = [f"{name}: not in the lock ({info['version']})" for name, info in libraries.items() if name not in locked]
    out += [f"{name}: in the lock, not in the environment" for name in locked if name not in libraries]
    for name, info in libraries.items():
        before = locked.get(name)
        if before is None:
            continue
        if before["version"] != info["version"]:
            out.append(f"{name}: {before['version']} in the lock, {info['version']} installed")
        elif before["files"] != info["files"]:
            out.append(f"{name} {info['version']}: its files are not the ones of the lock")
    return out


def check(verify: bool = False) -> list[str]:
    """Everything that keeps the environment from being the one of the lock (empty: it is)."""
    libraries, problems = current(verify)
    return problems + differences(libraries, read())


def wheel_tags(filename: str) -> set[str]:
    """The tags of a wheel file name («numpy-2.5.3-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl»)."""
    python, abi, platform = filename[:-4].split("-")[-3:]
    return {f"{p}-{a}-{q}" for p in python.split(".") for a in abi.split(".") for q in platform.split(".")}


def pypi(name: str, version: str, wanted: list[str]) -> dict:
    """The wheel of PyPI that was installed: its file, SHA-256 and the day it was published."""
    request = urllib.request.Request(f"https://pypi.org/pypi/{name}/{version}/json",
                                     headers={"User-Agent": "tensela-build", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as answer:
        files = json.load(answer)["urls"]
    for item in files:
        if item["packagetype"] == "bdist_wheel" and wheel_tags(item["filename"]) & set(wanted):
            return {"wheel": item["filename"], "sha256": item["digests"]["sha256"],
                    "published": item["upload_time_iso_8601"][:10]}
    raise LookupError(f"{name} {version}: no wheel on PyPI with the tags {wanted}")


def update(allow_young: bool) -> int:
    libraries, problems = current(verify=True)
    if problems:
        print("\n".join(problems))
        print("The environment has files that do not match their wheel: install it again before locking it.")
        return 1
    lock = read()
    today = dt.date.today()
    young = []
    for name, info in libraries.items():
        info.update(pypi(name, info["version"], info["tags"]))
        age = (today - dt.date.fromisoformat(info["published"])).days
        if age < COOL_DOWN_DAYS:
            young.append(f"{name} {info['version']}: published {info['published']} ({age} days ago)")
    for line in differences(libraries, lock):
        print("  changed:", line)
    if young:
        print(f"Younger than {COOL_DOWN_DAYS} days:\n  " + "\n  ".join(young))
        if not allow_young:
            print("Not written. Wait, or read what changed in them and give --allow-young.")
            return 1
    lock["libraries"] = libraries
    lock["written"] = today.isoformat()
    LOCK.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# The libraries of the AppImage, with the hashes of their wheels (written by tools/appimage_lock.py).",
             "# pip install --require-hashes --only-binary=:all: -r tools/appimage-requirements.txt"]
    lines += [f"{name}=={info['version']} --hash=sha256:{info['sha256']}" for name, info in libraries.items()]
    REQUIREMENTS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{LOCK.relative_to(ROOT)}: {len(libraries)} libraries")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--update", action="store_true", help="write the lock again (asks PyPI)")
    parser.add_argument("--allow-young", action="store_true",
                        help=f"accept versions published less than {COOL_DOWN_DAYS} days ago")
    args = parser.parse_args()
    if args.update:
        return update(args.allow_young)
    found = check(verify=True)
    print("\n".join(found) if found else f"the environment is the one of the lock ({LOCK.relative_to(ROOT)})")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
