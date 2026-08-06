"""Frameless top chrome: ☆ / status / settings·back + – □ ×.

All chrome buttons share BUTTON_H square footprint, soft shadow, and
crisp vector icons (no emoji / system glyphs).
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from app.ui.button_fx import BUTTON_H, apply_soft_button_shadow
from app.ui.win_chrome import start_system_move

_WIN_BTN_W = BUTTON_H
_WIN_BTN_H = BUTTON_H

# Stroke weight for 32px chrome icons (Windows / Fluent-like)
_ICON_STROKE = 1.35


class WindowControlButton(QPushButton):
    """
    Soft rounded-rect control with painted standard chrome icons.

    icon_kind:
      star | min | max | restore | close | settings | arrow_left
    """

    def __init__(
        self,
        text: str = "",
        *,
        kind: str = "normal",
        icon_kind: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(
            "WinCloseBtn" if kind == "close" else "WinChromeBtn"
        )
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFlat(True)
        self.setAutoDefault(False)
        self.setDefault(False)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.setContentsMargins(0, 0, 0, 0)
        self.setText("")  # always paint icons ourselves

        # Map legacy text-only construction to icon kinds
        if icon_kind:
            self._icon_kind = icon_kind
        else:
            self._icon_kind = {
                "☆": "star",
                "–": "min",
                "-": "min",
                "□": "max",
                "❐": "restore",
                "×": "close",
                "x": "close",
                "X": "close",
            }.get(text, "close" if kind == "close" else "max")

        self.setFixedSize(_WIN_BTN_W, _WIN_BTN_H)
        self.setMinimumSize(_WIN_BTN_W, _WIN_BTN_H)
        self.setMaximumSize(_WIN_BTN_W, _WIN_BTN_H)
        apply_soft_button_shadow(self, level="chrome")

    def set_icon_kind(self, icon_kind: str) -> None:
        if icon_kind == self._icon_kind:
            return
        self._icon_kind = icon_kind
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(_WIN_BTN_W, _WIN_BTN_H)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, event) -> None:  # noqa: N802
        # Background / border from QSS
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # Match QSS color: muted idle, text on hover (palette follows style)
        color = self.palette().color(self.foregroundRole())
        if not color.isValid() or color.alpha() == 0:
            color = QColor("#6e6e73")
        if not self.isEnabled():
            color.setAlpha(110)

        pen = QPen(color)
        pen.setWidthF(_ICON_STROKE)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        kind = self._icon_kind

        if kind == "star":
            self._paint_star(p, cx, cy, outer=6.2, inner=2.7)
        elif kind == "min":
            # Standard minimize: short horizontal bar
            p.drawLine(QPointF(cx - 5.0, cy), QPointF(cx + 5.0, cy))
        elif kind == "max":
            # Single square (maximize / fullscreen)
            r = QRectF(cx - 5.0, cy - 5.0, 10.0, 10.0)
            p.drawRoundedRect(r, 0.8, 0.8)
        elif kind == "restore":
            self._paint_restore(p, cx, cy, color)
        elif kind == "close":
            # Standard close: crisp X
            o = 4.6
            p.drawLine(QPointF(cx - o, cy - o), QPointF(cx + o, cy + o))
            p.drawLine(QPointF(cx + o, cy - o), QPointF(cx - o, cy + o))
        elif kind == "settings":
            # Same geometry as widgets._LineIcon("settings") — 6-tooth outline gear
            self._paint_gear(p, cx, cy, r=6.6)
        elif kind == "arrow_left":
            # ←
            p.drawLine(QPointF(cx - 5.0, cy), QPointF(cx + 5.0, cy))
            p.drawLine(QPointF(cx - 5.0, cy), QPointF(cx - 1.2, cy - 3.8))
            p.drawLine(QPointF(cx - 5.0, cy), QPointF(cx - 1.2, cy + 3.8))
        else:
            # Fallback: small disc
            p.drawEllipse(QPointF(cx, cy), 3.0, 3.0)

    @staticmethod
    def _paint_star(
        p: QPainter, cx: float, cy: float, *, outer: float, inner: float
    ) -> None:
        """Regular 5-point star outline (clear, symmetric)."""
        path = QPainterPath()
        for i in range(10):
            ang = -math.pi / 2.0 + i * math.pi / 5.0
            rad = outer if i % 2 == 0 else inner
            x = cx + rad * math.cos(ang)
            y = cy + rad * math.sin(ang)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
        p.drawPath(path)

    def _paint_restore(self, p: QPainter, cx: float, cy: float, color: QColor) -> None:
        """Two offset squares (Windows restore), front clears overlap with bg fill."""
        # Back window (upper-right)
        back = QRectF(cx - 2.0, cy - 6.0, 8.0, 8.0)
        p.drawRoundedRect(back, 0.6, 0.6)
        # Front window (lower-left) — fill with button bg so it covers back edge
        front = QRectF(cx - 6.0, cy - 2.0, 8.0, 8.0)
        bg = self.palette().color(self.backgroundRole())
        if not bg.isValid() or bg.alpha() == 0:
            bg = QColor("#ffffff")
        p.fillRect(front.adjusted(0.5, 0.5, -0.5, -0.5), bg)
        pen = p.pen()
        pen.setColor(color)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(front, 0.6, 0.6)

    @staticmethod
    def _paint_gear(p: QPainter, cx: float, cy: float, *, r: float) -> None:
        """
        Outline gear — same proportions as widgets._LineIcon settings:
        base ring + tooth protrusions + hub hole (not a crude star-gear).
        """
        # Match _LineIcon paint: outer = r*0.78, tooth bump = r*0.18, hub = r*0.32
        outer = r * 0.78
        tooth = r * 0.18
        hub = r * 0.32
        teeth = 6
        path = QPainterPath()
        for i in range(teeth * 2):
            ang = math.pi * i / teeth - math.pi / 2.0
            rad = outer + (tooth if i % 2 == 0 else 0.0)
            x = cx + rad * math.cos(ang)
            y = cy + rad * math.sin(ang)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
        p.drawPath(path)
        p.drawEllipse(QPointF(cx, cy), hub, hub)


class WindowTitleBar(QWidget):
    """
    Single top strip:
      [ left content… ]  ·stretch·  [ – □ × ]
    """

    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WindowTitleBar")
        self.setMinimumHeight(BUTTON_H + 12)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 12, 6)
        lay.setSpacing(6)

        self._leading = QHBoxLayout()
        self._leading.setContentsMargins(0, 0, 0, 0)
        self._leading.setSpacing(6)
        lay.addLayout(self._leading, 1)

        self.btn_min = WindowControlButton(icon_kind="min")
        self.btn_min.setToolTip("最小化")
        self.btn_min.clicked.connect(self.minimize_requested.emit)

        self.btn_max = WindowControlButton(icon_kind="max")
        self.btn_max.setToolTip("最大化")
        self.btn_max.clicked.connect(self.maximize_requested.emit)

        self.btn_close = WindowControlButton(icon_kind="close", kind="close")
        self.btn_close.setToolTip("关闭")
        self.btn_close.clicked.connect(self.close_requested.emit)

        for b in (self.btn_min, self.btn_max, self.btn_close):
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)

    def add_leading(
        self,
        widget: QWidget,
        stretch: int = 0,
        *,
        alignment: Qt.AlignmentFlag | Qt.Alignment = Qt.AlignmentFlag.AlignVCenter,
    ) -> None:
        self._leading.addWidget(widget, stretch, alignment)

    def add_leading_stretch(self, stretch: int = 1) -> None:
        self._leading.addStretch(stretch)

    def add_leading_spacing(self, px: int) -> None:
        self._leading.addSpacing(px)

    def control_buttons(self) -> list[QPushButton]:
        return [self.btn_min, self.btn_max, self.btn_close]

    def set_maximized_state(self, maximized: bool) -> None:
        if maximized:
            self.btn_max.set_icon_kind("restore")
            self.btn_max.setToolTip("还原")
        else:
            self.btn_max.set_icon_kind("max")
            self.btn_max.setToolTip("最大化")

    def _is_on_control(self, pos) -> bool:
        child = self.childAt(pos)
        while child is not None and child is not self:
            if isinstance(child, QPushButton):
                return True
            name = type(child).__name__
            if "Button" in name or "Slide" in name:
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
