"""Smooth frameless drag / resize helpers.

Prefer Qt system move/resize APIs. On Windows, fall back to SC_MOVE which
hands the drag loop to the OS (no per-pixel Python move() / setGeometry()).
"""

from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

_RESIZE_MARGIN = 8

# winuser
_WM_SYSCOMMAND = 0x0112
_SC_MOVE = 0xF010
_HTCAPTION = 2


def is_windows() -> bool:
    return sys.platform == "win32"


def start_system_move(window: QWidget) -> bool:
    """
    Begin an OS-driven window move from the current mouse press.
    Call from mousePressEvent (left button). Returns True if started.
    """
    if window is None:
        return False
    # Maximized: let OS snap-restore via system move when supported
    handle = window.windowHandle()
    if handle is not None:
        try:
            if handle.startSystemMove():
                return True
        except Exception:
            pass

    if is_windows():
        try:
            import ctypes

            hwnd = int(window.winId())
            ctypes.windll.user32.ReleaseCapture()
            # SC_MOVE | HTCAPTION → Windows runs the move modal loop
            ctypes.windll.user32.SendMessageW(
                hwnd, _WM_SYSCOMMAND, _SC_MOVE + _HTCAPTION, 0
            )
            return True
        except Exception:
            return False
    return False


def start_system_resize(window: QWidget, edges: Qt.Edge) -> bool:
    """Begin OS-driven edge resize. edges is a combination of Qt.Edge flags."""
    if window is None or not edges or window.isMaximized():
        return False
    handle = window.windowHandle()
    if handle is None:
        return False
    try:
        return bool(handle.startSystemResize(edges))
    except Exception:
        return False


def edges_at(window: QWidget, local_pos: QPoint, margin: int = _RESIZE_MARGIN) -> Qt.Edge:
    """Which window edges are under *local_pos* (widget coords of *window*)."""
    if window.isMaximized():
        return Qt.Edge(0)
    r = window.rect()
    edges = Qt.Edge(0)
    if local_pos.x() <= margin:
        edges |= Qt.Edge.LeftEdge
    if local_pos.x() >= r.width() - margin:
        edges |= Qt.Edge.RightEdge
    if local_pos.y() <= margin:
        edges |= Qt.Edge.TopEdge
    if local_pos.y() >= r.height() - margin:
        edges |= Qt.Edge.BottomEdge
    return edges


def cursor_for_edges(edges: Qt.Edge) -> Qt.CursorShape:
    left = bool(edges & Qt.Edge.LeftEdge)
    right = bool(edges & Qt.Edge.RightEdge)
    top = bool(edges & Qt.Edge.TopEdge)
    bottom = bool(edges & Qt.Edge.BottomEdge)
    if (left and top) or (right and bottom):
        return Qt.CursorShape.SizeFDiagCursor
    if (right and top) or (left and bottom):
        return Qt.CursorShape.SizeBDiagCursor
    if left or right:
        return Qt.CursorShape.SizeHorCursor
    if top or bottom:
        return Qt.CursorShape.SizeVerCursor
    return Qt.CursorShape.ArrowCursor


def map_to_window(window: QWidget, widget: QWidget, pos: QPoint) -> QPoint:
    return widget.mapTo(window, pos)
