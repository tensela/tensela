"""Inside the window: it listens on the local socket of protocol.py for the bridge, answers each tool (tools.py)
and keeps what was done, for the panel. Only the person can open the socket (it is a file of theirs, without a
network port). «Disconnect and pause» closes the connections and stops listening until «Allow again»."""
from __future__ import annotations

import json
import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer

from tensela.language import tr

from . import protocol, tools


class Server(QObject):
    changed = Signal()                                   # connected, paused, something done: the panel shows it

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.server: QLocalServer | None = None
        self.clients: dict[int, dict] = {}               # id of the connection → {"connection", "name", "buffer"}
        self.done: list[tuple[str, str, str, bool]] = []  # (time, AI program, what it did, went well)
        self.problem = ""
        self.mark = None

    # --- Listening ----------------------------------------------------------------------------------------------

    @property
    def listening(self) -> bool:
        return self.server is not None and self.server.isListening()

    def start(self) -> bool:
        if self.listening:
            return True
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(protocol.address()):
            QLocalServer.removeServer(protocol.address())  # left by a Tensela that did not end well
            if not server.listen(protocol.address()):
                self.problem = server.errorString()
                self.changed.emit()
                return False
        server.newConnection.connect(self._arrived)
        self.server, self.problem = server, ""
        self.changed.emit()
        return True

    def pause(self) -> None:
        """Disconnect and pause: no AI program can connect until start()."""
        for client in list(self.clients.values()):
            client["connection"].disconnectFromServer()
        self.clients.clear()
        if self.server is not None:
            self.server.close()
            self.server.deleteLater()
        self.server = None
        self._show_mark()
        self.changed.emit()

    def stop(self) -> None:
        """The extension turned off: everything closed, and the mark of the status bar gone."""
        self.pause()
        if self.mark is not None:
            self.window.statusBar().removeWidget(self.mark)
            self.mark.deleteLater()
            self.mark = None

    def connected(self) -> list[str]:
        return [c["name"] for c in self.clients.values()]

    # --- Connections ----------------------------------------------------------------------------------------------

    def _arrived(self) -> None:
        while self.server is not None and self.server.hasPendingConnections():
            connection = self.server.nextPendingConnection()
            key = id(connection)
            self.clients[key] = {"connection": connection, "name": tr('an AI program'), "buffer": b""}
            connection.readyRead.connect(lambda c=connection: self._read(c))
            connection.disconnected.connect(lambda k=key, c=connection: self._gone(k, c))
        self._show_mark()
        self.changed.emit()

    def _gone(self, key: int, connection) -> None:
        self.clients.pop(key, None)
        connection.deleteLater()
        self._show_mark()
        self.changed.emit()

    def _read(self, connection) -> None:
        client = self.clients.get(id(connection))
        if client is None:
            return
        client["buffer"] += bytes(connection.readAll())
        while b"\n" in client["buffer"]:
            text, client["buffer"] = client["buffer"].split(b"\n", 1)
            try:
                message = json.loads(text.decode("utf-8"))
            except ValueError:
                continue
            if "hello" in message:
                client["name"] = str(message["hello"])[:80] or client["name"]
                self.changed.emit()
                continue
            name = str(message.get("tool", ""))
            result, said = tools.call(self.window, name, message.get("arguments") or {})
            self.done.append((time.strftime("%H:%M:%S"), client["name"], said, not result.get("isError")))
            del self.done[:-200]
            connection.write(protocol.line({"id": message.get("id"), "result": result}))
            connection.flush()
            self.changed.emit()

    # --- The mark in the status bar -------------------------------------------------------------------------------

    def _show_mark(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QLabel
        if self.mark is None:
            self.mark = QLabel()
            self.mark.setObjectName("ai_connected")
            self.mark.setCursor(Qt.CursorShape.PointingHandCursor)
            self.mark.setToolTip(tr('An AI program is connected (AI connection): a click shows what it does'))
            self.mark.mousePressEvent = lambda _event: self.window.show_extension_panel("AI connection",
                                                                                        "ai-connection")
            self.window.statusBar().addPermanentWidget(self.mark)
        from tensela.ui import theme
        self.mark.setText(f"<span style='color:{theme.color('accent', '#5b4bf0')}'>●</span> {tr('AI connected')}")
        self.mark.setVisible(bool(self.clients))
