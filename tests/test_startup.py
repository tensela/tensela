"""The window starts from its command (tensela-app), with its options in English and the old ones."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

EXAMPLES = Path(__file__).resolve().parent / "data"


@pytest.mark.parametrize("options", [["--seconds", "0.5", "--style", "sobrio"], ["--segundos", "0.5", "--estilo", "sobrio"]])
def test_the_window_starts_from_its_command(options, tmp_path):
    # In its own process and with its own preferences: the window saves them on closing (recent files, size…).
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path), "QT_QPA_PLATFORM": "offscreen"}
    code = "import sys; from tensela.ui.window import main; sys.exit(main(sys.argv[1:]))"
    done = subprocess.run([sys.executable, "-c", code, str(EXAMPLES / "caso_01.json"), *options], env=env,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    name = "Tensela.ini" if sys.platform == "win32" else "Tensela.conf"   # (Windows: a file too, not the registry)
    assert (tmp_path / "Tensela" / name).exists()                  # the preferences went there
