"""The lock of the AppImage (tools/appimage_lock.py): it reads the hashes of a RECORD and the tags of a wheel, and it
sees any library that changed version or files."""
import base64
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import appimage_lock as L  # noqa: E402


def test_record_hash_is_the_sha256_in_hexadecimal():
    digest = hashlib.sha256(b"tensela").digest()
    value = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    assert L.record_hash(f"sha256={value}") == digest.hex()
    assert L.record_hash("") is None
    assert L.record_hash("md5=abc") is None


def test_wheel_tags_expand_the_compressed_ones():
    tags = L.wheel_tags("numpy-2.5.3-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl")
    assert tags == {"cp313-cp313-manylinux_2_27_x86_64", "cp313-cp313-manylinux_2_28_x86_64"}
    assert L.wheel_tags("six-1.17.0-py2.py3-none-any.whl") == {"py2-none-any", "py3-none-any"}


def test_differences_see_versions_files_and_names():
    lock = {"libraries": {"a": {"version": "1", "files": "x"}, "b": {"version": "2", "files": "y"},
                          "gone": {"version": "1", "files": "z"}}}
    now = {"a": {"version": "1", "files": "x"}, "b": {"version": "2", "files": "changed"},
           "new": {"version": "3", "files": "w"}}
    found = L.differences(now, lock)
    assert found == ["new: not in the lock (3)", "gone: in the lock, not in the environment",
                     "b 2: its files are not the ones of the lock"]
    now["b"]["version"] = "2.1"
    assert "b: 2 in the lock, 2.1 installed" in L.differences(now, lock)
    assert L.differences({"a": {"version": "1", "files": "x"}}, {"libraries": {"a": {"version": "1", "files": "x"}}}) \
        == []
