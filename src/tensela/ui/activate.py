"""Bringing the open window to the front when another start of Tensela asks for it (ui/launch.py).

The desktop does not let a window take the focus by itself (it would steal it from what the person is doing); GNOME
shows «Tensela is ready» instead. What it accepts is the permission that comes with the start the person asked for:
the desktop gives each program it starts an activation token (XDG_ACTIVATION_TOKEN on Wayland, DESKTOP_STARTUP_ID on
X11). The second start hands its token to the open window, which uses it:

- on Wayland, Qt asks for the focus with the token in XDG_ACTIVATION_TOKEN;
- on X11 (and XWayland, where Tensela runs on GNOME), the window gets the token in its property _NET_STARTUP_ID: the
  window manager then activates it, as for a window that was just opened.

Started from a terminal there is no token, and the desktop decides as before.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os


def tokens() -> dict:
    """The activation tokens this start got from the desktop (to hand over)."""
    return {key: os.environ[key] for key in ("XDG_ACTIVATION_TOKEN", "DESKTOP_STARTUP_ID") if os.environ.get(key)}


class _Screen(ctypes.Structure):
    _fields_ = [("root", ctypes.c_uint32)]                     # the first field of xcb_screen_t


class _ScreenIterator(ctypes.Structure):
    _fields_ = [("data", ctypes.POINTER(_Screen)), ("rem", ctypes.c_int), ("index", ctypes.c_int)]


class _AtomCookie(ctypes.Structure):
    _fields_ = [("sequence", ctypes.c_uint)]


class _AtomReply(ctypes.Structure):
    _fields_ = [("response_type", ctypes.c_uint8), ("pad0", ctypes.c_uint8), ("sequence", ctypes.c_uint16),
                ("length", ctypes.c_uint32), ("atom", ctypes.c_uint32)]


def x11_startup_id(window_id: int, startup_id: str) -> bool:
    """Puts `startup_id` in the property _NET_STARTUP_ID of the X11 window `window_id` (through its own connection to
    the X server). Returns whether it could."""
    name = ctypes.util.find_library("xcb")
    libc_name = ctypes.util.find_library("c")
    if not name or not libc_name or not os.environ.get("DISPLAY"):
        return False
    try:
        xcb, libc = ctypes.CDLL(name), ctypes.CDLL(libc_name)
        xcb.xcb_connect.restype = ctypes.c_void_p
        xcb.xcb_connect.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
        xcb.xcb_connection_has_error.argtypes = [ctypes.c_void_p]
        xcb.xcb_intern_atom.restype = _AtomCookie
        xcb.xcb_intern_atom.argtypes = [ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint16, ctypes.c_char_p]
        xcb.xcb_intern_atom_reply.restype = ctypes.POINTER(_AtomReply)
        xcb.xcb_intern_atom_reply.argtypes = [ctypes.c_void_p, _AtomCookie, ctypes.c_void_p]
        xcb.xcb_change_property.argtypes = [ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint32, ctypes.c_uint32,
                                            ctypes.c_uint32, ctypes.c_uint8, ctypes.c_uint32, ctypes.c_char_p]
        xcb.xcb_flush.argtypes = [ctypes.c_void_p]
        xcb.xcb_disconnect.argtypes = [ctypes.c_void_p]
        libc.free.argtypes = [ctypes.c_void_p]
        connection = xcb.xcb_connect(None, None)
        if not connection:
            return False
        try:
            if xcb.xcb_connection_has_error(connection):
                return False

            def atom(text: bytes) -> int:
                reply = xcb.xcb_intern_atom_reply(connection, xcb.xcb_intern_atom(connection, 0, len(text), text),
                                                  None)
                if not reply:
                    return 0
                value = reply.contents.atom
                libc.free(ctypes.cast(reply, ctypes.c_void_p))
                return value

            prop, kind = atom(b"_NET_STARTUP_ID"), atom(b"UTF8_STRING")
            if not prop or not kind:
                return False
            data = startup_id.encode("utf-8")
            xcb.xcb_change_property(connection, 0, window_id, prop, kind, 8, len(data), data)   # 0: replace
            xcb.xcb_flush(connection)
            return True
        finally:
            xcb.xcb_disconnect(connection)
    except (OSError, AttributeError, ValueError):
        return False


def bring_forward(window, given: dict) -> None:
    """`window` (a QWidget, already shown) to the front, with the tokens another start handed over (see `tokens`)."""
    from PySide6.QtGui import QGuiApplication
    if window.isMinimized():
        window.showNormal()
    platform = QGuiApplication.platformName()
    token = given.get("XDG_ACTIVATION_TOKEN") or given.get("DESKTOP_STARTUP_ID")
    if token and platform == "xcb":
        x11_startup_id(int(window.winId()), given.get("DESKTOP_STARTUP_ID") or token)
    elif token and platform.startswith("wayland"):
        os.environ["XDG_ACTIVATION_TOKEN"] = token             # Qt takes it from here when it asks for the focus
    window.raise_()
    window.activateWindow()
