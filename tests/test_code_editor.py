"""The editor of the Code node (plan of the pending work, 2.12; Victor, test 72): its helps while writing and its
colours, letter and helps from Preferences."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = r'''
import os, sys
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QApplication
app = QApplication([]); app.setOrganizationName("Tensela"); app.setApplicationName("Tensela")
from tensela import language
language.LANGUAGE = "en"
from tensela.ui import code_editor
from tensela.ui.code_editor import CodeDialog, PALETTES

def key(widget, k, text="", mods=Qt.KeyboardModifier.NoModifier):
    widget.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, k, mods, text))

def run():
    d = CodeDialog("c", "x = 1\ny = 2\n", None); d.show(); app.processEvents()
    code = d.code
    end = code.textCursor(); end.movePosition(QTextCursor.MoveOperation.End); code.setTextCursor(end)
    # Brackets and quotes
    key(code, Qt.Key.Key_ParenLeft, "(")
    assert code.toPlainText().endswith("()"), repr(code.toPlainText())
    key(code, Qt.Key.Key_ParenRight, ")")                       # stepped over, not doubled
    assert code.toPlainText().endswith("()") and code.textCursor().atEnd()
    key(code, Qt.Key.Key_Left); key(code, Qt.Key.Key_Backspace)  # both go
    assert code.toPlainText().endswith("2\n"), repr(code.toPlainText())
    key(code, Qt.Key.Key_QuoteDbl, '"')
    assert code.toPlainText().endswith('""')
    key(code, Qt.Key.Key_Backspace)
    # Comment and uncomment the two first lines, as one step each
    cursor = code.textCursor(); cursor.setPosition(0)
    cursor.setPosition(len("x = 1\ny"), QTextCursor.MoveMode.KeepAnchor); code.setTextCursor(cursor)
    key(code, Qt.Key.Key_Slash, "/", Qt.KeyboardModifier.ControlModifier)
    assert code.toPlainText().startswith("# x = 1\n# y = 2"), repr(code.toPlainText())
    key(code, Qt.Key.Key_Slash, "/", Qt.KeyboardModifier.ControlModifier)
    assert code.toPlainText().startswith("x = 1\ny = 2"), repr(code.toPlainText())
    # In and out
    key(code, Qt.Key.Key_Tab)
    assert code.toPlainText().startswith("    x = 1\n    y = 2"), repr(code.toPlainText())
    key(code, Qt.Key.Key_Backtab)
    assert code.toPlainText().startswith("x = 1\ny = 2")
    # Find and replace
    d.show_find(True); d.wanted.setText("y"); d.instead.setText("height")
    assert code.find("y") and code.textCursor().selectedText() == "y"
    assert d.code.replace_all("y", "height") == 1 and "height = 2" in code.toPlainText()
    d._found(code.find("nothing")); assert "not in the code" in d.status.text()
    # Names suggested
    end = code.textCursor(); end.movePosition(QTextCursor.MoveOperation.End); code.setTextCursor(end)
    code.insertPlainText("po")
    code._suggest(force=True); app.processEvents()
    assert code._completer.currentCompletion() == "point", code._completer.currentCompletion()
    code._insert_completion("point")
    assert code.toPlainText().endswith("point")
    # Colours and letter from Preferences
    QSettings().setValue("code/colours", "contrast"); QSettings().setValue("code/size", 16.0)
    QSettings().setValue("code/pairs", False)
    d.restyle()
    assert code.colours == PALETTES["contrast"] and code.font().pointSizeF() == 16 and not code.pairs
    key(code, Qt.Key.Key_ParenLeft, "(")
    assert code.toPlainText().endswith("point(")                  # without closing it now
    code.zoom(+1); assert code.font().pointSizeF() == 17 and float(QSettings().value("code/size")) == 17
    print("ok", flush=True)
    os._exit(0)

def safely():
    try:
        run()
    except Exception:
        import traceback
        traceback.print_exc()
        os._exit(4)

QTimer.singleShot(300, safely)
QTimer.singleShot(60000, lambda: os._exit(3))
app.exec()
'''


def test_the_helps_of_the_code_editor(tmp_path):
    pytest.importorskip("PySide6")
    script = tmp_path / "editor.py"
    script.write_text(SCRIPT, encoding="utf-8")
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"), "QT_QPA_PLATFORM": "offscreen",
           "PYTHONPATH": str(Path(__file__).parent.parent / "src")}
    result = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True, timeout=90)
    assert "ok" in result.stdout, result.stdout[-2000:] + result.stderr[-4000:]
