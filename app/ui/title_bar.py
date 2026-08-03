"""Frameless-window chrome: drag region + min / max / close.

Dragging uses OS system-move (see win_chrome.start_system_move) — never
a Python per-frame window.move() loop.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from app.ui.win_chrome import start_system_move


class WindowControlButton(QPushButton):
    """Round capsule control matching ActionBtn height."""

    def __init__(self, text: str, *, kind: str = "normal", parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName(
            "WinCloseBtn" if kind == "close" else "WinChromeBtn"
        )
        self.setFixedSize(36, 28)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)


class WindowTitleBar(QWidget):
    """Slim top strip: drag pad · window buttons."""

    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WindowTitleBar")
        self.setFixedHeight(36)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 4, 12, 0)
        lay.setSpacing(6)

        self.brand = QLabel("")
        self.brand.setObjectName("TitleBarBrand")
        self.brand.hide()

        # Empty stretch: mouse goes through to title bar → start_system_move
        self._drag_pad = QWidget()
        self._drag_pad.setObjectName("TitleBarDragPad")
        self._drag_pad.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._drag_pad.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        lay.addWidget(self._drag_pad, 1)

        self.btn_min = WindowControlButton("–")
        self.btn_min.setToolTip("最小化")
        self.btn_min.clicked.connect(self.minimize_requested.emit)

        self.btn_max = WindowControlButton("□")
        self.btn_max.setToolTip("最大化")
        self.btn_max.clicked.connect(self.maximize_requested.emit)

        self.btn_close = WindowControlButton("×", kind="close")
        self.btn_close.setToolTip("关闭")
        self.btn_close.clicked.connect(self.close_requested.emit)

        for b in (self.btn_min, self.btn_max, self.btn_close):
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)

    def control_buttons(self) -> list[QPushButton]:
        return [self.btn_min, self.btn_max, self.btn_close]

    def set_maximized_state(self, maximized: bool) -> None:
        if maximized:
            self.btn_max.setText("❐")
            self.btn_max.setToolTip("还原")
        else:
            self.btn_max.setText("□")
            self.btn_max.setToolTip("最大化")

    def _is_on_control(self, pos) -> bool:
        child = self.childAt(pos)
        while child is not None and child is not self:
            if isinstance(child, QPushButton):
                return True
            child = child.parentWidget()
        return False

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_on_control(event.position().toPoint()):
                super().mousePressEvent(event)
                return
            win = self.window()
            if win is not None and start_system_move(win):
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._is_on_control(event.position().toPoint()):
                self.maximize_requested.emit()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)
