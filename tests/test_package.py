import tensela


def test_the_package_imports():
    assert tensela.__version__


def test_the_version_is_the_same_in_both_places():
    """The version of the package (pyproject.toml) and the one Tensela shows (and names the AppImage with)."""
    import re
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^version = "([^"]+)"', text, re.M).group(1) == tensela.__version__
