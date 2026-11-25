"""What every test shares."""


def pytest_sessionfinish(session, exitstatus):
    """The windows the tests left open, closed and deleted while Qt is whole. Left for the end, PySide destroys them
    when Python closes, after parts of them (a 3D view) are gone, and the run crashes after every test passed."""
    import sys
    if "PySide6.QtWidgets" not in sys.modules:
        return
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return
    QApplication.clipboard().clear()
    for widget in QApplication.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
