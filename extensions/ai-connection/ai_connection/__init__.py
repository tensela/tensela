"""AI connection: an AI program of the person's choice looks at the open project and changes it (each step undone
with Ctrl+Z; Code nodes and files ask the person first), through MCP.

The AI program starts the bridge (`--extension ai-connection`: bridge.py), which speaks MCP with it and hands each
tool to the open window through a local socket of the person (protocol.py). In the window, server.py answers with
tools.py (to look) and changes.py (to change), and the panel shows what it does. Tensela does not connect to any
service: the AI program the person set up is the one that connects, inside the computer.
"""
from __future__ import annotations

#: The server of the window (only in the window: not in the bridge nor in the process that computes).
SERVER = None


def start(window) -> None:
    global SERVER
    if SERVER is None:
        from .server import Server
        SERVER = Server(window)
    SERVER.start()


def panel(window):
    start(window)
    from .panel import ConnectionPanel
    return ConnectionPanel(window, SERVER)


def run_bridge(arguments: list[str]) -> int:
    from .bridge import main
    return main(arguments)


def unregister() -> None:
    global SERVER
    if SERVER is not None:
        SERVER.stop()
        SERVER.deleteLater()
        SERVER = None


def register(tensela) -> None:
    tensela.command(run_bridge, "The bridge an AI program starts: MCP on its standard input and output")
    tensela.panel("AI connection", panel,
                  "Your AI program talks with this window: what it may do and what it did")
    tensela.on("window", start)
