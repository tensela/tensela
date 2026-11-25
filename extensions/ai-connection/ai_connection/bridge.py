"""The bridge: the command the AI program starts (`--extension ai-connection`). It speaks MCP with the AI program
on its standard input and output (JSON-RPC, one message per line) and hands each tool to the open window, through
the local socket of protocol.py. Without Qt and without the window: it starts at once.
"""
from __future__ import annotations

import json
import socket
import sys

from . import protocol

#: What a tool may take, at most (a computation, an image of the view, the person deciding).
TIMEOUT = 900.0                  # (it may wait for the person: Allow / Do not allow)
CLOSED = ("Tensela is not open, or its AI connection is off or paused. Ask the person to open Tensela and turn on "
          "«AI connection» (Extensions → Manage extensions…), or to press «Allow again» in its panel.")


class Window:
    """The connection with the open window (made again if it was lost)."""

    def __init__(self):
        self.connection: socket.socket | None = None
        self.buffer = b""
        self.client = "an AI program"
        self.turn = 0

    def _connect(self) -> None:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(TIMEOUT)
        connection.connect(protocol.address())
        connection.sendall(protocol.line({"hello": self.client}))
        self.connection, self.buffer = connection, b""

    def call(self, tool: str, arguments: dict) -> dict:
        for attempt in (1, 2):                          # once again if the window was opened again meanwhile
            try:
                if self.connection is None:
                    self._connect()
                self.turn += 1
                self.connection.sendall(protocol.line({"id": self.turn, "tool": tool, "arguments": arguments}))
                while b"\n" not in self.buffer:
                    data = self.connection.recv(1 << 20)
                    if not data:
                        raise ConnectionError("closed")
                    self.buffer += data
                text, self.buffer = self.buffer.split(b"\n", 1)
                return json.loads(text.decode("utf-8"))["result"]
            except (OSError, ConnectionError, ValueError, KeyError):
                self.close()
        return {"content": [{"type": "text", "text": CLOSED}], "isError": True}

    def close(self) -> None:
        if self.connection is not None:
            try:
                self.connection.close()
            except OSError:
                pass
        self.connection = None


def answer(message: dict, window: Window) -> dict | None:
    """The answer to one message of the AI program (None for a notification)."""
    method, ident, params = message.get("method"), message.get("id"), message.get("params") or {}
    if ident is None:                                   # notifications: initialized, cancelled…
        return None

    def ok(result):
        return {"jsonrpc": "2.0", "id": ident, "result": result}

    if method == "initialize":
        asked = params.get("protocolVersion")
        info = params.get("clientInfo") or {}
        window.client = str(info.get("title") or info.get("name") or window.client)[:80]
        from tensela import __version__
        return ok({"protocolVersion": asked if asked in protocol.VERSIONS else protocol.VERSIONS[0],
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": "tensela", "title": "Tensela", "version": __version__},
                   "instructions": protocol.INSTRUCTIONS})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": protocol.TOOLS})
    if method == "tools/call":
        name = params.get("name")
        if name not in protocol.BY_NAME:
            return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32602, "message": f"Unknown tool: {name}"}}
        return ok(window.call(name, params.get("arguments") or {}))
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main(arguments: list[str], reading=None, writing=None) -> int:
    reading = reading or sys.stdin.buffer
    writing = writing or sys.stdout.buffer
    window = Window()
    for raw in reading:
        if not raw.strip():
            continue
        try:
            message = json.loads(raw.decode("utf-8"))
        except ValueError:
            writing.write(protocol.line({"jsonrpc": "2.0", "id": None,
                                         "error": {"code": -32700, "message": "Parse error"}}))
            writing.flush()
            continue
        batch = message if isinstance(message, list) else [message]
        answers = [a for a in (answer(m, window) for m in batch if isinstance(m, dict)) if a is not None]
        if answers:
            writing.write(protocol.line(answers if isinstance(message, list) else answers[0]))
            writing.flush()
    window.close()
    return 0
