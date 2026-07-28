from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import (
    Qt,
    Signal,
    QEvent,
    QMimeData,
    QUrl,
    QPoint,
    QPointF,
    QSize,
    QTimer,
    QVariantAnimation,
    QEasingCurve,
    QAbstractAnimation,
)
from PySide6.QtGui import (
    QColor,
    QDrag,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QFont,
    QMouseEvent,
    QEnterEvent,
    QPainterPath,
    QPalette,
    QRegion,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
import math


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}


def _make_icon_surface_transparent(w: QWidget) -> None:
    """Icons must not inherit global QWidget solid background from theme QSS."""
    w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    w.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
    w.setAutoFillBackground(False)
    # Beat global `QWidget { background: ... }` stylesheet
    w.setStyleSheet("background: transparent; border: none;")
    pal = w.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor(0, 0, 0, 0))
    pal.setColor(QPalette.ColorRole.Base, QColor(0, 0, 0, 0))
    w.setPalette(pal)


class _LineIcon(QWidget):
    """Stroke icons; opacity/rotation via QPainter (no graphics effects)."""

    def __init__(self, kind: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._kind = kind  # "settings" | "arrow" | "arrow_left"
        self._opacity = 1.0
        self._rotation = 0.0  # degrees
        self._color_override: Optional[QColor] = None
        self.setObjectName("SlideSettingsIcon")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        _make_icon_surface_transparent(self)
        self.setFixedSize(16, 16)

    def set_opacity(self, opacity: float) -> None:
        o = max(0.0, min(1.0, float(opacity)))
        if abs(o - self._opacity) < 0.001:
            return
        self._opacity = o
        self.update()

    def set_rotation(self, degrees: float) -> None:
        d = float(degrees)
        if abs(d - self._rotation) < 0.05:
            return
        self._rotation = d
        self.update()

    def set_color_override(self, color: Optional[QColor]) -> None:
        """Force stroke color (ignores palette / QSS). None = use palette."""
        self._color_override = QColor(color) if color is not None else None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._opacity <= 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setOpacity(self._opacity)
        if self._color_override is not None and self._color_override.isValid():
            color = self._color_override
        else:
            color = self.palette().color(QPalette.ColorRole.WindowText)
            if not color.isValid() or color.alpha() == 0:
                color = self.palette().color(QPalette.ColorRole.Text)
        pen = QPen(color)
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        r = min(self.width(), self.height()) / 2.0 - 1.0

        if abs(self._rotation) > 0.01:
            p.translate(cx, cy)
            p.rotate(self._rotation)
            p.translate(-cx, -cy)

        if self._kind == "arrow":
            # →
            x0, x1 = cx - 5.5, cx + 5.5
            p.drawLine(QPointF(x0, cy), QPointF(x1 - 1.5, cy))
            p.drawLine(QPointF(x1 - 4.5, cy - 3.5), QPointF(x1, cy))
            p.drawLine(QPointF(x1 - 4.5, cy + 3.5), QPointF(x1, cy))
            return

        if self._kind == "arrow_left":
            # ←
            x0, x1 = cx - 5.5, cx + 5.5
            p.drawLine(QPointF(x0 + 1.5, cy), QPointF(x1, cy))
            p.drawLine(QPointF(x0 + 4.5, cy - 3.5), QPointF(x0, cy))
            p.drawLine(QPointF(x0 + 4.5, cy + 3.5), QPointF(x0, cy))
            return

        if self._kind == "broom":
            # Simple broom (扫帚): handle + brush head — clear button
            # Handle (diagonal stick)
            p.drawLine(QPointF(cx + 4.5, cy - 5.5), QPointF(cx - 1.0, cy + 1.5))
            # Ferrule / band
            p.drawLine(QPointF(cx - 2.2, cy + 0.2), QPointF(cx + 0.8, cy + 2.8))
            # Brush bristles (fan)
            base = QPointF(cx - 0.5, cy + 1.8)
            for dx, dy in (
                (-5.5, 3.5),
                (-4.0, 5.0),
                (-2.0, 5.8),
                (0.0, 6.0),
                (1.5, 5.2),
            ):
                p.drawLine(base, QPointF(cx + dx, cy + dy))
            return

        if self._kind == "refresh":
            # lucide RefreshCw
            rr = r * 0.72
            p.drawArc(
                int(cx - rr),
                int(cy - rr),
                int(rr * 2),
                int(rr * 2),
                40 * 16,
                200 * 16,
            )
            tip = QPointF(cx + rr * 0.55, cy - rr * 0.75)
            p.drawLine(tip, QPointF(tip.x() - 3.2, tip.y() - 0.5))
            p.drawLine(tip, QPointF(tip.x() + 0.2, tip.y() + 3.2))
            p.drawArc(
                int(cx - rr),
                int(cy - rr),
                int(rr * 2),
                int(rr * 2),
                220 * 16,
                200 * 16,
            )
            tip2 = QPointF(cx - rr * 0.55, cy + rr * 0.75)
            p.drawLine(tip2, QPointF(tip2.x() + 3.2, tip2.y() + 0.5))
            p.drawLine(tip2, QPointF(tip2.x() - 0.2, tip2.y() - 3.2))
            return

        # settings — outline gear
        outer = r * 0.78
        inner = r * 0.32
        teeth = 6
        path = QPainterPath()
        for i in range(teeth * 2):
            ang = math.pi * i / teeth - math.pi / 2
            rad = outer + (r * 0.18 if i % 2 == 0 else 0.0)
            x = cx + rad * math.cos(ang)
            y = cy + rad * math.sin(ang)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
        p.drawPath(path)
        p.drawEllipse(QPointF(cx, cy), inner, inner)


class _CapsuleShell(QWidget):
    """
    Self-painted fully-rounded capsule (pill).
    QSS border-radius on QFrame is unreliable on Windows; paint guarantees round ends.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SlideSettingsBtn")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._hovered = False
        self._pressed = False
        self._disabled = False
        self._fill_primary = False  # solid primary (export)
        # Filled from theme via apply_theme_colors (no hard-coded final palette)
        self._bg = QColor("#ffffff")
        self._border = QColor("#d2d2d7")
        self._bg_hover = QColor("#fafafa")
        self._bg_pressed = QColor("#f0f0f2")
        self._bg_disabled = QColor("#f5f5f7")
        self._border_hover = QColor("#34c759")
        self._border_disabled = QColor("#d2d2d7")
        self._primary = QColor("#34c759")

    def set_fill_primary(self, on: bool) -> None:
        self._fill_primary = bool(on)
        self.update()

    def set_state(self, *, hovered: bool, pressed: bool, disabled: bool) -> None:
        self._hovered = hovered
        self._pressed = pressed
        self._disabled = disabled
        self.update()

    def apply_theme_colors(
        self,
        *,
        bg: str,
        border: str,
        hover: str,
        pressed: str,
        disabled_bg: str,
        primary: str,
    ) -> None:
        self._bg = QColor(bg)
        self._border = QColor(border)
        self._bg_hover = QColor(hover)
        self._bg_pressed = QColor(pressed)
        self._bg_disabled = QColor(disabled_bg)
        self._border_hover = QColor(primary)
        self._border_disabled = QColor(border)
        self._primary = QColor(primary)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Inset half-pixel so 1px stroke sits fully inside and stays round
        r = self.rect().adjusted(1, 1, -1, -1)
        if r.width() < 2 or r.height() < 2:
            return
        radius = r.height() / 2.0  # full pill ends — never square

        if self._fill_primary:
            base = QColor(self._primary)
            if self._disabled:
                bg = QColor(base)
                bg.setAlpha(110)
                border = QColor(bg)
            elif self._pressed:
                bg = base.darker(115)
                border = bg
            elif self._hovered:
                bg = base.lighter(118)
                border = bg
            else:
                bg = base
                border = base
        elif self._disabled:
            bg, border = self._bg_disabled, self._border_disabled
        elif self._pressed:
            bg, border = self._bg_pressed, self._border
        elif self._hovered:
            bg, border = self._bg_hover, self._border_hover
        else:
            bg, border = self._bg, self._border

        path = QPainterPath()
        path.addRoundedRect(
            float(r.x()),
            float(r.y()),
            float(r.width()),
            float(r.height()),
            radius,
            radius,
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawPath(path)
        pen = QPen(border)
        pen.setWidthF(1.0)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


class SlideCapsuleButton(QFrame):
    """
    Reusable capsule control: one QVariantAnimation t∈[0,1]
    (reflow + icon slide + fade + scale). No QGraphicsOpacityEffect.

    idle  →  [left_icon] text
    hover →  text [right_icon]
    """

    clicked = Signal()

    _BASE_H = 36
    _ICON = 16
    _SLIDE = 10
    _PAD_X = 24
    _GAP = 10
    _DUR_HOVER = 360
    _DUR_PRESS = 140

    def __init__(
        self,
        *,
        text: str = "设置",
        left_kind: str = "settings",
        right_kind: str = "arrow",
        tooltip: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SlideSettingsHost")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._hovered = False
        self._pressed = False
        self._enabled = True
        self._t = 0.0  # 0 idle → 1 hover
        self._caption_w = 28
        self._text_color = "#1d1d1f"
        self._disabled_text = "#a1a1a6"

        self.shell = _CapsuleShell(self)

        self.icon_left = _LineIcon(left_kind, self.shell)
        self.icon_left.set_opacity(1.0)

        self.caption = QLabel(text, self.shell)
        self.caption.setObjectName("SlideSettingsText")
        self.caption.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self.caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.icon_right = _LineIcon(right_kind, self.shell)
        self.icon_right.set_opacity(0.0)

        # Single timeline — created once, reused
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(0.0)
        self._anim.setDuration(self._DUR_HOVER)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_t)

        if tooltip:
            self.setToolTip(tooltip)
        self._cache_caption_width()
        base = self._base_size()
        self._host_w = int(round(base.width() * 1.06)) + 2
        self._host_h = int(round(base.height() * 1.06)) + 2
        self.setFixedSize(self._host_w, self._host_h)
        self._apply_layout()

    def apply_theme_colors(
        self,
        *,
        bg: str,
        border: str,
        hover: str,
        pressed: str,
        disabled_bg: str,
        primary: str,
        text: str,
        disabled_text: str,
    ) -> None:
        self.shell.apply_theme_colors(
            bg=bg,
            border=border,
            hover=hover,
            pressed=pressed,
            disabled_bg=disabled_bg,
            primary=primary,
        )
        self._text_color = text
        self._disabled_text = disabled_text
        self._apply_fg_colors()

    def _apply_fg_colors(self) -> None:
        col = QColor(
            self._text_color if self._enabled else self._disabled_text
        )
        for w in (self.icon_left, self.icon_right, self.caption):
            pal = w.palette()
            pal.setColor(QPalette.ColorRole.WindowText, col)
            pal.setColor(QPalette.ColorRole.Text, col)
            w.setPalette(pal)
            w.update()

    def _cache_caption_width(self) -> None:
        self.caption.adjustSize()
        self._caption_w = max(self.caption.sizeHint().width(), 24)

    def _base_size(self) -> QSize:
        w = self._PAD_X * 2 + self._ICON + self._GAP + self._caption_w
        return QSize(w, self._BASE_H)

    def _scale_now(self) -> float:
        if self._pressed and self._enabled:
            return 0.96
        # hover scale rides on t
        return 1.0 + 0.02 * self._t

    def _on_t(self, value) -> None:
        self._t = float(value)
        self._apply_layout()

    def _apply_layout(self) -> None:
        t = self._t
        scale = self._scale_now()
        base = self._base_size()
        sw = max(1, int(round(base.width() * scale)))
        sh = max(1, int(round(base.height() * scale)))
        self.shell.setGeometry(
            (self._host_w - sw) // 2,
            (self._host_h - sh) // 2,
            sw,
            sh,
        )

        tw = self._caption_w
        left_span = self._ICON * (1.0 - t)
        right_span = self._ICON * t
        gap_l = self._GAP * (1.0 - t)
        gap_r = self._GAP * t
        content_w = left_span + gap_l + tw + gap_r + right_span
        inner = max(0, sw - 2 * self._PAD_X)
        start = self._PAD_X + max(0.0, (inner - content_w) / 2.0)

        row_h = self._ICON
        row_y = max(0, (sh - row_h) // 2)
        left_slide = -self._SLIDE * t
        right_slide = self._SLIDE * (1.0 - t)

        self.icon_left.setGeometry(
            int(round(start + left_slide)), row_y, self._ICON, row_h
        )
        self.icon_left.set_opacity(1.0 - t)

        self.caption.setGeometry(
            int(round(start + left_span + gap_l)), row_y, tw, row_h
        )

        right_x = start + left_span + gap_l + tw + gap_r + right_slide
        self.icon_right.setGeometry(
            int(round(right_x)), row_y, self._ICON, row_h
        )
        self.icon_right.set_opacity(t)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_layout()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_layout()

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        self._enabled = bool(enabled)
        super().setEnabled(enabled)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if enabled
            else Qt.CursorShape.ForbiddenCursor
        )
        if not enabled:
            self._hovered = False
            self._pressed = False
            self._anim.stop()
            self._t = 0.0
            self._apply_layout()
        self._sync_shell()
        self._apply_fg_colors()

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802
        super().enterEvent(event)
        if self._enabled:
            self._hovered = True
            self._sync_shell()
            self._animate_t(1.0)

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self._hovered = False
        self._pressed = False
        self._sync_shell()
        if self._enabled:
            self._animate_t(0.0)
        else:
            self._anim.stop()
            self._t = 0.0
            self._apply_layout()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._enabled:
            self._pressed = True
            self._sync_shell()
            self._apply_layout()  # scale only — no full re-anim
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._enabled:
            was = self._pressed
            self._pressed = False
            self._sync_shell()
            self._apply_layout()
            if was and self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _sync_shell(self) -> None:
        self.shell.set_state(
            hovered=self._hovered and self._enabled,
            pressed=self._pressed and self._enabled,
            disabled=not self._enabled,
        )

    def _animate_t(self, target: float) -> None:
        target = 1.0 if target >= 0.5 else 0.0
        if abs(self._t - target) < 0.001 and (
            self._anim.state() != QAbstractAnimation.State.Running
        ):
            return
        running = self._anim.state() == QAbstractAnimation.State.Running
        cur = float(self._anim.currentValue()) if running else self._t
        self._anim.stop()
        self._anim.setStartValue(cur)
        self._anim.setEndValue(target)
        self._anim.setDuration(
            self._DUR_PRESS if self._pressed else self._DUR_HOVER
        )
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def set_text(self, text: str) -> None:
        self.caption.setText(text)
        self._cache_caption_width()
        base = self._base_size()
        self._host_w = int(round(base.width() * 1.06)) + 2
        self._host_h = int(round(base.height() * 1.06)) + 2
        self.setFixedSize(self._host_w, self._host_h)
        self._apply_layout()


class SlideSettingsButton(SlideCapsuleButton):
    """Main-window「设置」entry."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            text="设置",
            left_kind="settings",
            right_kind="arrow",
            tooltip="打开设置",
            parent=parent,
        )


class SlideBackButton(QFrame):
    """
    Settings-page「返回」per text.md RotateButton:
    fixed [settings gear][gap][返回]; hover rotates gear 180° + scale 1.02;
    press scale 0.96. Single QVariantAnimation, no graphics effects.
    """

    clicked = Signal()

    _BASE_H = 36
    _ICON = 16
    _PAD_X = 24
    _GAP = 10  # ml-2.5
    _DUR_HOVER = 380
    _DUR_PRESS = 140

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SlideSettingsHost")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._hovered = False
        self._pressed = False
        self._enabled = True
        self._t = 0.0  # 0 idle → 1 hover (rotation + scale)
        self._caption_w = 28
        self._text_color = "#1d1d1f"
        self._disabled_text = "#a1a1a6"

        self.shell = _CapsuleShell(self)

        # Fixed 16×16 slot for gear (matches reference relative wrapper)
        self.icon_slot = QWidget(self.shell)
        self.icon_slot.setObjectName("SlideSettingsSlot")
        self.icon_slot.setFixedSize(self._ICON, self._ICON)
        self.icon_slot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        _make_icon_surface_transparent(self.icon_slot)

        self.icon = _LineIcon("settings", self.icon_slot)
        self.icon.setGeometry(0, 0, self._ICON, self._ICON)
        self.icon.set_opacity(1.0)
        self.icon.set_rotation(0.0)

        self.caption = QLabel("返回", self.shell)
        self.caption.setObjectName("SlideSettingsText")
        self.caption.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self.caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(0.0)
        self._anim.setDuration(self._DUR_HOVER)
        # Spring-like: mild overshoot (framer stiffness 400 / damping 25)
        ease = QEasingCurve(QEasingCurve.Type.OutBack)
        ease.setOvershoot(1.25)
        self._anim.setEasingCurve(ease)
        self._anim.valueChanged.connect(self._on_t)

        self.setToolTip("返回主界面（不会因按 Esc 退出）")
        self._cache_caption_width()
        base = self._base_size()
        self._host_w = int(round(base.width() * 1.06)) + 2
        self._host_h = int(round(base.height() * 1.06)) + 2
        self.setFixedSize(self._host_w, self._host_h)
        self._apply_layout()

    def apply_theme_colors(
        self,
        *,
        bg: str,
        border: str,
        hover: str,
        pressed: str,
        disabled_bg: str,
        primary: str,
        text: str,
        disabled_text: str,
    ) -> None:
        self.shell.apply_theme_colors(
            bg=bg,
            border=border,
            hover=hover,
            pressed=pressed,
            disabled_bg=disabled_bg,
            primary=primary,
        )
        self._text_color = text
        self._disabled_text = disabled_text
        self._apply_fg_colors()

    def _apply_fg_colors(self) -> None:
        col = QColor(self._text_color if self._enabled else self._disabled_text)
        for w in (self.icon, self.caption):
            pal = w.palette()
            pal.setColor(QPalette.ColorRole.WindowText, col)
            pal.setColor(QPalette.ColorRole.Text, col)
            w.setPalette(pal)
            w.update()

    def _cache_caption_width(self) -> None:
        self.caption.adjustSize()
        self._caption_w = max(self.caption.sizeHint().width(), 24)

    def _base_size(self) -> QSize:
        # px-6 + icon + ml-2.5 + text
        w = self._PAD_X * 2 + self._ICON + self._GAP + self._caption_w
        return QSize(w, self._BASE_H)

    def _scale_now(self) -> float:
        if self._pressed and self._enabled:
            return 0.96
        return 1.0 + 0.02 * self._t

    def _on_t(self, value) -> None:
        self._t = float(value)
        self.icon.set_rotation(180.0 * self._t)
        self._apply_layout()

    def _apply_layout(self) -> None:
        scale = self._scale_now()
        base = self._base_size()
        sw = max(1, int(round(base.width() * scale)))
        sh = max(1, int(round(base.height() * scale)))
        self.shell.setGeometry(
            (self._host_w - sw) // 2,
            (self._host_h - sh) // 2,
            sw,
            sh,
        )

        tw = self._caption_w
        content_w = self._ICON + self._GAP + tw
        inner = max(0, sw - 2 * self._PAD_X)
        start = self._PAD_X + max(0.0, (inner - content_w) / 2.0)
        row_y = max(0, (sh - self._ICON) // 2)

        self.icon_slot.setGeometry(int(round(start)), row_y, self._ICON, self._ICON)
        self.caption.setGeometry(
            int(round(start + self._ICON + self._GAP)),
            row_y,
            tw,
            self._ICON,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_layout()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_layout()

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        self._enabled = bool(enabled)
        super().setEnabled(enabled)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if enabled
            else Qt.CursorShape.ForbiddenCursor
        )
        if not enabled:
            self._hovered = False
            self._pressed = False
            self._anim.stop()
            self._t = 0.0
            self.icon.set_rotation(0.0)
            self._apply_layout()
        self._sync_shell()
        self._apply_fg_colors()

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802
        super().enterEvent(event)
        if self._enabled:
            self._hovered = True
            self._sync_shell()
            self._animate_t(1.0)

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self._hovered = False
        self._pressed = False
        self._sync_shell()
        if self._enabled:
            self._animate_t(0.0)
        else:
            self._anim.stop()
            self._t = 0.0
            self.icon.set_rotation(0.0)
            self._apply_layout()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._enabled:
            self._pressed = True
            self._sync_shell()
            self._apply_layout()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._enabled:
            was = self._pressed
            self._pressed = False
            self._sync_shell()
            self._apply_layout()
            if was and self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _sync_shell(self) -> None:
        self.shell.set_state(
            hovered=self._hovered and self._enabled,
            pressed=self._pressed and self._enabled,
            disabled=not self._enabled,
        )

    def _animate_t(self, target: float) -> None:
        target = 1.0 if target >= 0.5 else 0.0
        if abs(self._t - target) < 0.001 and (
            self._anim.state() != QAbstractAnimation.State.Running
        ):
            return
        running = self._anim.state() == QAbstractAnimation.State.Running
        cur = float(self._anim.currentValue()) if running else self._t
        self._anim.stop()
        self._anim.setStartValue(cur)
        self._anim.setEndValue(target)
        self._anim.setDuration(
            self._DUR_PRESS if self._pressed else self._DUR_HOVER
        )
        ease = QEasingCurve(QEasingCurve.Type.OutBack)
        ease.setOvershoot(1.25)
        self._anim.setEasingCurve(
            QEasingCurve.Type.OutCubic if self._pressed else ease
        )
        self._anim.start()


class _MorphFolderIcon(QWidget):
    """
    Line-style Folder ↔ FolderOpen (text.md MorphButton).
    Idle: theme text color stroke; hover (t→1): primary green stroke.
    No fill — outline only.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._t = 0.0
        self._disabled = False
        self._color_idle = QColor("#1d1d1f")
        self._color_hover = QColor("#34c759")  # theme primary; updated via set_colors
        self._color_disabled = QColor("#A1A1A6")
        self.setObjectName("SlideSettingsIcon")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        _make_icon_surface_transparent(self)
        self.setFixedSize(16, 16)

    def set_t(self, t: float) -> None:
        v = max(0.0, min(1.0, float(t)))
        if abs(v - self._t) < 0.002:
            return
        self._t = v
        self.update()

    def set_disabled_look(self, disabled: bool) -> None:
        if self._disabled == disabled:
            return
        self._disabled = bool(disabled)
        self.update()

    def set_colors(self, *, idle: str, hover: str, disabled: str) -> None:
        """idle = theme text; hover = theme primary green."""
        self._color_idle = QColor(idle)
        self._color_hover = QColor(hover)
        self._color_disabled = QColor(disabled)
        self.update()

    def _stroke_color(self) -> QColor:
        if self._disabled:
            return self._color_disabled
        # lerp idle → green with hover progress t
        a, b = self._color_idle, self._color_hover
        t = self._t
        return QColor(
            int(a.red() + (b.red() - a.red()) * t),
            int(a.green() + (b.green() - a.green()) * t),
            int(a.blue() + (b.blue() - a.blue()) * t),
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = self._stroke_color()
        pen = QPen(color)
        pen.setWidthF(1.55)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        t = self._t

        closed_op = 1.0 - t
        open_op = t
        closed_sc = 0.5 + 0.5 * (1.0 - t)
        open_sc = 0.5 + 0.5 * t

        if closed_op > 0.02:
            p.save()
            p.setOpacity(closed_op)
            p.translate(cx, cy)
            p.scale(closed_sc, closed_sc)
            p.translate(-cx, -cy)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            self._paint_folder_closed(p, cx, cy)
            p.restore()

        if open_op > 0.02:
            p.save()
            p.setOpacity(open_op)
            p.translate(cx, cy)
            p.scale(open_sc, open_sc)
            p.translate(-cx, -cy)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            self._paint_folder_open(p, cx, cy)
            p.restore()

    @staticmethod
    def _paint_folder_closed(p: QPainter, cx: float, cy: float) -> None:
        path = QPainterPath()
        path.moveTo(cx - 6.2, cy - 2.2)
        path.lineTo(cx - 6.2, cy - 4.0)
        path.lineTo(cx - 2.2, cy - 4.0)
        path.lineTo(cx - 0.6, cy - 2.2)
        path.lineTo(cx + 6.2, cy - 2.2)
        path.lineTo(cx + 6.2, cy + 4.5)
        path.lineTo(cx - 6.2, cy + 4.5)
        path.closeSubpath()
        p.drawPath(path)

    @staticmethod
    def _paint_folder_open(p: QPainter, cx: float, cy: float) -> None:
        back = QPainterPath()
        back.moveTo(cx - 6.2, cy - 1.5)
        back.lineTo(cx - 6.2, cy - 3.8)
        back.lineTo(cx - 2.0, cy - 3.8)
        back.lineTo(cx - 0.5, cy - 2.0)
        back.lineTo(cx + 5.5, cy - 2.0)
        back.lineTo(cx + 5.5, cy + 1.2)
        p.drawPath(back)
        front = QPainterPath()
        front.moveTo(cx - 6.5, cy + 0.8)
        front.lineTo(cx - 4.5, cy + 4.6)
        front.lineTo(cx + 6.5, cy + 4.6)
        front.lineTo(cx + 4.8, cy + 0.8)
        front.closeSubpath()
        p.drawPath(front)


class SlideOpenButton(QFrame):
    """
    Main-window「打开…」per text.md MorphButton:
    fixed [folder morph][gap][打开…]; hover Folder→FolderOpen (scale+opacity);
    button scale 1.02 / 0.96. Single timeline, painted capsule.
    """

    clicked = Signal()

    _BASE_H = 36
    _ICON = 16
    _PAD_X = 24
    _GAP = 10
    _DUR_HOVER = 360
    _DUR_PRESS = 140

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SlideSettingsHost")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._hovered = False
        self._pressed = False
        self._enabled = True
        self._t = 0.0
        self._caption_w = 36
        self._text_color = "#1d1d1f"
        self._disabled_text = "#a1a1a6"

        self.shell = _CapsuleShell(self)

        self.icon_slot = QWidget(self.shell)
        self.icon_slot.setObjectName("SlideSettingsSlot")
        self.icon_slot.setFixedSize(self._ICON, self._ICON)
        self.icon_slot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        _make_icon_surface_transparent(self.icon_slot)

        self.icon = _MorphFolderIcon(self.icon_slot)
        self.icon.setGeometry(0, 0, self._ICON, self._ICON)

        self.caption = QLabel("打开…", self.shell)
        self.caption.setObjectName("SlideSettingsText")
        self.caption.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self.caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(0.0)
        self._anim.setDuration(self._DUR_HOVER)
        ease = QEasingCurve(QEasingCurve.Type.OutBack)
        ease.setOvershoot(1.2)
        self._anim.setEasingCurve(ease)
        self._anim.valueChanged.connect(self._on_t)

        self.setToolTip("打开图片文件")
        self._cache_caption_width()
        base = self._base_size()
        self._host_w = int(round(base.width() * 1.06)) + 2
        self._host_h = int(round(base.height() * 1.06)) + 2
        self.setFixedSize(self._host_w, self._host_h)
        self._apply_layout()

    def apply_theme_colors(
        self,
        *,
        bg: str,
        border: str,
        hover: str,
        pressed: str,
        disabled_bg: str,
        primary: str,
        text: str,
        disabled_text: str,
    ) -> None:
        self.shell.apply_theme_colors(
            bg=bg,
            border=border,
            hover=hover,
            pressed=pressed,
            disabled_bg=disabled_bg,
            primary=primary,
        )
        self._text_color = text
        self._disabled_text = disabled_text
        # Folder line: idle = text color, hover = primary green
        self.icon.set_colors(idle=text, hover=primary, disabled=disabled_text)
        self._apply_fg_colors()

    def _apply_fg_colors(self) -> None:
        col = QColor(self._text_color if self._enabled else self._disabled_text)
        pal = self.caption.palette()
        pal.setColor(QPalette.ColorRole.WindowText, col)
        pal.setColor(QPalette.ColorRole.Text, col)
        self.caption.setPalette(pal)
        self.caption.update()
        self.icon.set_disabled_look(not self._enabled)
        self.icon.update()

    def _cache_caption_width(self) -> None:
        self.caption.adjustSize()
        self._caption_w = max(self.caption.sizeHint().width(), 28)

    def _base_size(self) -> QSize:
        w = self._PAD_X * 2 + self._ICON + self._GAP + self._caption_w
        return QSize(w, self._BASE_H)

    def _scale_now(self) -> float:
        if self._pressed and self._enabled:
            return 0.96
        return 1.0 + 0.02 * self._t

    def _on_t(self, value) -> None:
        self._t = float(value)
        self.icon.set_t(self._t)
        self._apply_layout()

    def _apply_layout(self) -> None:
        scale = self._scale_now()
        base = self._base_size()
        sw = max(1, int(round(base.width() * scale)))
        sh = max(1, int(round(base.height() * scale)))
        self.shell.setGeometry(
            (self._host_w - sw) // 2,
            (self._host_h - sh) // 2,
            sw,
            sh,
        )
        tw = self._caption_w
        content_w = self._ICON + self._GAP + tw
        inner = max(0, sw - 2 * self._PAD_X)
        start = self._PAD_X + max(0.0, (inner - content_w) / 2.0)
        row_y = max(0, (sh - self._ICON) // 2)
        self.icon_slot.setGeometry(int(round(start)), row_y, self._ICON, self._ICON)
        self.caption.setGeometry(
            int(round(start + self._ICON + self._GAP)),
            row_y,
            tw,
            self._ICON,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_layout()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_layout()

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        self._enabled = bool(enabled)
        super().setEnabled(enabled)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if enabled
            else Qt.CursorShape.ForbiddenCursor
        )
        if not enabled:
            self._hovered = False
            self._pressed = False
            self._anim.stop()
            self._t = 0.0
            self.icon.set_t(0.0)
            self._apply_layout()
        self._sync_shell()
        self._apply_fg_colors()

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802
        super().enterEvent(event)
        if self._enabled:
            self._hovered = True
            self._sync_shell()
            self._animate_t(1.0)

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self._hovered = False
        self._pressed = False
        self._sync_shell()
        if self._enabled:
            self._animate_t(0.0)
        else:
            self._anim.stop()
            self._t = 0.0
            self.icon.set_t(0.0)
            self._apply_layout()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._enabled:
            self._pressed = True
            self._sync_shell()
            self._apply_layout()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._enabled:
            was = self._pressed
            self._pressed = False
            self._sync_shell()
            self._apply_layout()
            if was and self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _sync_shell(self) -> None:
        self.shell.set_state(
            hovered=self._hovered and self._enabled,
            pressed=self._pressed and self._enabled,
            disabled=not self._enabled,
        )

    def _animate_t(self, target: float) -> None:
        target = 1.0 if target >= 0.5 else 0.0
        if abs(self._t - target) < 0.001 and (
            self._anim.state() != QAbstractAnimation.State.Running
        ):
            return
        running = self._anim.state() == QAbstractAnimation.State.Running
        cur = float(self._anim.currentValue()) if running else self._t
        self._anim.stop()
        self._anim.setStartValue(cur)
        self._anim.setEndValue(target)
        self._anim.setDuration(
            self._DUR_PRESS if self._pressed else self._DUR_HOVER
        )
        ease = QEasingCurve(QEasingCurve.Type.OutBack)
        ease.setOvershoot(1.2)
        self._anim.setEasingCurve(
            QEasingCurve.Type.OutCubic if self._pressed else ease
        )
        self._anim.start()


class SlideClearButton(QFrame):
    """
    Main-window「清除」: outline capsule + broom icon.
    Hover broom sweep: 0° → -45° → +45° → 0° (left 45, right 90, left 45).
    Button scale 1.02 / press 0.96 like other capsules.
    """

    clicked = Signal()

    _BASE_H = 36
    _ICON = 16
    _PAD_X = 24  # px-6
    _GAP = 10  # ml-2.5
    _DUR_SWEEP = 720  # one full broom cycle
    _DUR_PRESS = 140

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SlideSettingsHost")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._hovered = False
        self._pressed = False
        self._enabled = True
        self._sweep_t = 0.0  # 0..1 broom cycle
        self._caption_w = 28
        self._text_color = "#1d1d1f"
        self._disabled_text = "#a1a1a6"

        self.shell = _CapsuleShell(self)
        self.shell.set_fill_primary(False)

        self.icon_slot = QWidget(self.shell)
        self.icon_slot.setObjectName("SlideSettingsSlot")
        self.icon_slot.setFixedSize(self._ICON, self._ICON)
        self.icon_slot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        _make_icon_surface_transparent(self.icon_slot)

        self.icon = _LineIcon("broom", self.icon_slot)
        self.icon.setGeometry(0, 0, self._ICON, self._ICON)
        self.icon.set_opacity(1.0)
        self.icon.set_rotation(0.0)

        self.caption = QLabel("清除", self.shell)
        self.caption.setObjectName("SlideSettingsText")
        self.caption.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self.caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(self._DUR_SWEEP)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._anim.valueChanged.connect(self._on_sweep)
        self._anim.finished.connect(self._on_sweep_finished)

        self.setToolTip("清除勾选的图片。仅一张时清除当前图；多图请先勾选。")
        self._cache_caption_width()
        base = self._base_size()
        self._host_w = int(round(base.width() * 1.06)) + 2
        self._host_h = int(round(base.height() * 1.06)) + 2
        self.setFixedSize(self._host_w, self._host_h)
        self._apply_layout()
        self.setEnabled(False)

    @staticmethod
    def _broom_angle(t: float) -> float:
        """
        One sweep cycle t∈[0,1]:
          0 → 1/3 : 0° → -45°  (left 45°)
          1/3 → 2/3 : -45° → +45°  (right 90°)
          2/3 → 1 : +45° → 0°  (left 45° back)
        """
        t = max(0.0, min(1.0, float(t)))
        if t < 1.0 / 3.0:
            u = t * 3.0
            return -45.0 * u
        if t < 2.0 / 3.0:
            u = (t - 1.0 / 3.0) * 3.0
            return -45.0 + 90.0 * u
        u = (t - 2.0 / 3.0) * 3.0
        return 45.0 * (1.0 - u)

    def apply_theme_colors(
        self,
        *,
        bg: str,
        border: str,
        hover: str,
        pressed: str,
        disabled_bg: str,
        primary: str,
        text: str,
        disabled_text: str,
    ) -> None:
        self.shell.apply_theme_colors(
            bg=bg,
            border=border,
            hover=hover,
            pressed=pressed,
            disabled_bg=disabled_bg,
            primary=primary,
        )
        self.shell.set_fill_primary(False)
        self._text_color = text
        self._disabled_text = disabled_text
        self._apply_fg_colors()

    def _apply_fg_colors(self) -> None:
        col = QColor(self._text_color if self._enabled else self._disabled_text)
        self.icon.set_color_override(col)
        pal = self.caption.palette()
        pal.setColor(QPalette.ColorRole.WindowText, col)
        pal.setColor(QPalette.ColorRole.Text, col)
        self.caption.setPalette(pal)
        self.caption.update()
        self.icon.update()

    def set_text(self, text: str) -> None:
        self.caption.setText(text or "清除")
        self._cache_caption_width()
        base = self._base_size()
        self._host_w = int(round(base.width() * 1.06)) + 2
        self._host_h = int(round(base.height() * 1.06)) + 2
        self.setFixedSize(self._host_w, self._host_h)
        self._apply_layout()

    def _cache_caption_width(self) -> None:
        self.caption.adjustSize()
        self._caption_w = max(self.caption.sizeHint().width(), 24)

    def _base_size(self) -> QSize:
        w = self._PAD_X * 2 + self._ICON + self._GAP + self._caption_w
        return QSize(w, self._BASE_H)

    def _scale_now(self) -> float:
        if self._pressed and self._enabled:
            return 0.96
        if self._hovered and self._enabled:
            return 1.02
        return 1.0

    def _on_sweep(self, value) -> None:
        self._sweep_t = float(value)
        self.icon.set_rotation(self._broom_angle(self._sweep_t))
        self._apply_layout()

    def _on_sweep_finished(self) -> None:
        # Loop sweep while still hovered
        if self._hovered and self._enabled:
            self._play_sweep()
        else:
            self._sweep_t = 0.0
            self.icon.set_rotation(0.0)
            self._apply_layout()

    def _play_sweep(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(self._DUR_SWEEP)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._anim.start()

    def _stop_sweep(self) -> None:
        self._anim.stop()
        self._sweep_t = 0.0
        self.icon.set_rotation(0.0)
        self._apply_layout()

    def _apply_layout(self) -> None:
        scale = self._scale_now()
        base = self._base_size()
        sw = max(1, int(round(base.width() * scale)))
        sh = max(1, int(round(base.height() * scale)))
        self.shell.setGeometry(
            (self._host_w - sw) // 2,
            (self._host_h - sh) // 2,
            sw,
            sh,
        )
        tw = self._caption_w
        content_w = self._ICON + self._GAP + tw
        inner = max(0, sw - 2 * self._PAD_X)
        start = self._PAD_X + max(0.0, (inner - content_w) / 2.0)
        row_y = max(0, (sh - self._ICON) // 2)
        self.icon_slot.setGeometry(int(round(start)), row_y, self._ICON, self._ICON)
        self.caption.setGeometry(
            int(round(start + self._ICON + self._GAP)),
            row_y,
            tw,
            self._ICON,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_layout()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_layout()

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        self._enabled = bool(enabled)
        super().setEnabled(enabled)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if enabled
            else Qt.CursorShape.ForbiddenCursor
        )
        if not enabled:
            self._hovered = False
            self._pressed = False
            self._stop_sweep()
        self._sync_shell()
        self._apply_fg_colors()

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802
        super().enterEvent(event)
        if self._enabled:
            self._hovered = True
            self._sync_shell()
            self._apply_layout()
            self._play_sweep()

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self._hovered = False
        self._pressed = False
        self._sync_shell()
        self._stop_sweep()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._enabled:
            self._pressed = True
            self._sync_shell()
            self._apply_layout()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._enabled:
            was = self._pressed
            self._pressed = False
            self._sync_shell()
            self._apply_layout()
            if was and self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _sync_shell(self) -> None:
        self.shell.set_state(
            hovered=self._hovered and self._enabled,
            pressed=self._pressed and self._enabled,
            disabled=not self._enabled,
        )


class SlideExportButton(QFrame):
    """
    Main-window「导出」— same surface as 打开/设置 (outline capsule, theme text).
    TextReveal motion: arrow 45° + dual-line y-slide + scale.
    Keep Qt enabled always; gate real export in the clicked slot.
    """

    clicked = Signal()

    _BASE_H = 36
    _ICON = 16
    _PAD_X = 22
    _GAP = 10
    _TEXT_H = 18
    _DUR_HOVER = 360
    _DUR_PRESS = 140

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SlideSettingsHost")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._hovered = False
        self._pressed = False
        self._t = 0.0
        self._caption = "导出"
        self._caption_w = 36
        self._text_color = "#1d1d1f"
        self._disabled_text = "#a1a1a6"

        # Same outline pill as 打开/设置 — NOT solid primary green
        self.shell = _CapsuleShell(self)
        self.shell.set_fill_primary(False)

        self.icon_slot = QWidget(self.shell)
        self.icon_slot.setObjectName("SlideSettingsSlot")
        self.icon_slot.setFixedSize(self._ICON, self._ICON)
        self.icon_slot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        _make_icon_surface_transparent(self.icon_slot)

        self.icon = _LineIcon("arrow", self.icon_slot)
        self.icon.setGeometry(0, 0, self._ICON, self._ICON)
        self.icon.set_opacity(1.0)
        self.icon.set_rotation(0.0)

        self.text_clip = QWidget(self.shell)
        self.text_clip.setObjectName("SlideSettingsSlot")
        self.text_clip.setFixedHeight(self._TEXT_H)
        self.text_clip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        _make_icon_surface_transparent(self.text_clip)

        self._text_stack = QWidget(self.text_clip)
        self._text_stack.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        _make_icon_surface_transparent(self._text_stack)

        self.caption_a = QLabel(self._caption, self._text_stack)
        self.caption_b = QLabel(self._caption, self._text_stack)
        for cap in (self.caption_a, self.caption_b):
            cap.setObjectName("SlideSettingsText")
            cap.setAlignment(
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
            )
            cap.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(0.0)
        self._anim.setDuration(self._DUR_HOVER)
        ease = QEasingCurve(QEasingCurve.Type.OutBack)
        ease.setOvershoot(1.2)
        self._anim.setEasingCurve(ease)
        self._anim.valueChanged.connect(self._on_t)

        self.setToolTip("导出处理结果")
        self._cache_caption_width()
        base = self._base_size()
        self._host_w = int(round(base.width() * 1.06)) + 2
        self._host_h = int(round(base.height() * 1.06)) + 2
        self.setFixedSize(self._host_w, self._host_h)
        self._apply_layout()
        self._sync_shell()

    def apply_theme_colors(
        self,
        *,
        bg: str,
        border: str,
        hover: str,
        pressed: str,
        disabled_bg: str,
        primary: str,
        text: str,
        disabled_text: str,
    ) -> None:
        self.shell.apply_theme_colors(
            bg=bg,
            border=border,
            hover=hover,
            pressed=pressed,
            disabled_bg=disabled_bg,
            primary=primary,
        )
        self.shell.set_fill_primary(False)
        self._text_color = text
        self._disabled_text = disabled_text
        self._apply_fg_colors()

    def _apply_fg_colors(self) -> None:
        col = QColor(self._text_color)
        self.icon.set_color_override(col)
        for cap in (self.caption_a, self.caption_b):
            pal = cap.palette()
            pal.setColor(QPalette.ColorRole.WindowText, col)
            pal.setColor(QPalette.ColorRole.Text, col)
            cap.setPalette(pal)
            cap.update()
        self.icon.update()

    def set_text(self, text: str) -> None:
        self._caption = text or "导出"
        self.caption_a.setText(self._caption)
        self.caption_b.setText(self._caption)
        self._cache_caption_width()
        base = self._base_size()
        self._host_w = int(round(base.width() * 1.06)) + 2
        self._host_h = int(round(base.height() * 1.06)) + 2
        self.setFixedSize(self._host_w, self._host_h)
        self._apply_layout()

    def text(self) -> str:
        return self._caption

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        """Keep interactive like 设置/打开; export slot gates real work."""
        del enabled
        super().setEnabled(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sync_shell()

    def _cache_caption_width(self) -> None:
        self.caption_a.adjustSize()
        self._caption_w = max(self.caption_a.sizeHint().width() + 4, 32)

    def _base_size(self) -> QSize:
        w = self._PAD_X * 2 + self._ICON + self._GAP + self._caption_w
        return QSize(w, self._BASE_H)

    def _scale_now(self) -> float:
        if self._pressed:
            return 0.96
        return 1.0 + 0.02 * self._t

    def _on_t(self, value) -> None:
        self._t = float(value)
        self.icon.set_rotation(45.0 * self._t)
        self._apply_layout()

    def _apply_layout(self) -> None:
        scale = self._scale_now()
        base = self._base_size()
        sw = max(1, int(round(base.width() * scale)))
        sh = max(1, int(round(base.height() * scale)))
        self.shell.setGeometry(
            (self._host_w - sw) // 2,
            (self._host_h - sh) // 2,
            sw,
            sh,
        )
        tw = self._caption_w
        content_w = self._ICON + self._GAP + tw
        inner = max(0, sw - 2 * self._PAD_X)
        start = self._PAD_X + max(0.0, (inner - content_w) / 2.0)
        row_y = max(0, (sh - self._ICON) // 2)
        self.icon_slot.setGeometry(int(round(start)), row_y, self._ICON, self._ICON)

        text_x = int(round(start + self._ICON + self._GAP))
        text_y = max(0, (sh - self._TEXT_H) // 2)
        self.text_clip.setGeometry(text_x, text_y, tw, self._TEXT_H)
        self.text_clip.setMask(QRegion(0, 0, max(tw, 1), self._TEXT_H))
        slide = int(round(-self._TEXT_H * self._t))
        self._text_stack.setGeometry(0, slide, tw, self._TEXT_H * 2)
        self.caption_a.setGeometry(0, 0, tw, self._TEXT_H)
        self.caption_b.setGeometry(0, self._TEXT_H, tw, self._TEXT_H)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_layout()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_layout()

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802
        super().enterEvent(event)
        self._hovered = True
        self._sync_shell()
        self._animate_t(1.0)

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self._hovered = False
        self._pressed = False
        self._sync_shell()
        self._animate_t(0.0)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._sync_shell()
            self._apply_layout()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            was = self._pressed
            self._pressed = False
            self._sync_shell()
            self._apply_layout()
            if was and self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _sync_shell(self) -> None:
        self.shell.set_state(
            hovered=self._hovered,
            pressed=self._pressed,
            disabled=False,
        )

    def _animate_t(self, target: float) -> None:
        target = 1.0 if target >= 0.5 else 0.0
        if abs(self._t - target) < 0.001 and (
            self._anim.state() != QAbstractAnimation.State.Running
        ):
            return
        running = self._anim.state() == QAbstractAnimation.State.Running
        cur = float(self._anim.currentValue()) if running else self._t
        self._anim.stop()
        self._anim.setStartValue(cur)
        self._anim.setEndValue(target)
        self._anim.setDuration(
            self._DUR_PRESS if self._pressed else self._DUR_HOVER
        )
        ease = QEasingCurve(QEasingCurve.Type.OutBack)
        ease.setOvershoot(1.2)
        self._anim.setEasingCurve(
            QEasingCurve.Type.OutCubic if self._pressed else ease
        )
        self._anim.start()


# Mark drag-out so dropping the result back onto Peel does not re-import it.
PEEL_INTERNAL_MIME = "application/x-peel-internal-drag"
_internal_drag_depth = 0


def begin_internal_drag_out() -> None:
    global _internal_drag_depth
    _internal_drag_depth += 1


def end_internal_drag_out() -> None:
    global _internal_drag_depth
    _internal_drag_depth = max(0, _internal_drag_depth - 1)


def is_internal_drag_out() -> bool:
    return _internal_drag_depth > 0


def mime_is_peel_internal(mime: QMimeData) -> bool:
    """True if this drag was started by Peel result drag-out."""
    try:
        return mime.hasFormat(PEEL_INTERNAL_MIME)
    except Exception:
        return False


def should_ignore_drop(mime: QMimeData) -> bool:
    """Ignore drops that come from our own drag-out (or while it is active)."""
    return is_internal_drag_out() or mime_is_peel_internal(mime)


def path_from_mime(mime: QMimeData) -> Optional[Path]:
    paths = paths_from_mime(mime)
    return paths[0] if paths else None


def paths_from_mime(mime: QMimeData) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        try:
            key = str(p.resolve())
        except Exception:
            key = str(p)
        if key in seen:
            return
        if p.suffix.lower() in IMAGE_EXTENSIONS and p.is_file():
            seen.add(key)
            out.append(p)

    if mime.hasUrls():
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            p = Path(url.toLocalFile())
            if p.is_file():
                add(p)
            elif p.is_dir():
                for child in sorted(p.iterdir()):
                    add(child)
    if not out and mime.hasText():
        text = mime.text().strip().strip('"')
        if text.lower().startswith("file:"):
            p = Path(QUrl(text).toLocalFile())
        else:
            p = Path(text)
        add(p)
    return out


def is_supported_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS and path.is_file()


def pil_to_qpixmap(image) -> QPixmap:
    """Convert PIL Image (RGBA) to QPixmap."""
    from PIL import Image

    if not isinstance(image, Image.Image):
        raise TypeError("expected PIL Image")
    rgba = image if image.mode == "RGBA" else image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimg = QImage(data, rgba.width, rgba.height, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimg)


def scale_plain(pix: QPixmap, avail: QSize) -> QPixmap:
    return pix.scaled(
        avail,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class FitPixmapLabel(QLabel):
    """
    QLabel that does NOT grow its sizeHint to the pixmap size.

    Default QLabel.sizeHint() returns the full pixmap size, which blows up
    layouts and makes chrome (compare button / hints) sit on top of the image.
    Always scale content to the widget rect externally via setPixmap.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.setMinimumSize(80, 80)
        self.setScaledContents(False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(200, 200)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(80, 80)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return False


def scale_with_checker(
    pix: QPixmap,
    avail: QSize,
    checker_a: str,
    checker_b: str,
) -> QPixmap:
    scaled = scale_plain(pix, avail)
    board = make_checkerboard(
        scaled.size(), color_a=checker_a, color_b=checker_b
    )
    painter = QPainter(board)
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    return board


def compose_side_by_side(
    original: QPixmap,
    result: QPixmap,
    avail: QSize,
    checker_a: str,
    checker_b: str,
    *,
    flip_left: bool = False,
    flip_right: bool = False,
) -> QPixmap:
    """
    Left = original, right = result (checkerboard).
    flip_left / flip_right: temporarily show the other image in that slot
    (long-press peek, same idea as single-view hold).
    """
    gap = 10
    label_h = 22
    half_w = max((avail.width() - gap) // 2, 40)
    img_h = max(avail.height() - label_h, 40)
    half = QSize(half_w, img_h)

    # left normally original (plain); flip → result with checker
    if flip_left:
        left = scale_with_checker(result, half, checker_a, checker_b)
        left_label = "结果"
    else:
        left = scale_plain(original, half)
        left_label = "原图"

    # right normally result (checker); flip → original plain
    if flip_right:
        right = scale_plain(original, half)
        right_label = "原图"
    else:
        right = scale_with_checker(result, half, checker_a, checker_b)
        right_label = "结果"

    h = max(left.height(), right.height()) + label_h
    w = left.width() + gap + right.width()
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.drawPixmap(0, 0, left)
    p.drawPixmap(left.width() + gap, 0, right)
    p.setPen(QColor("#6e6e73"))
    font = QFont()
    font.setPointSize(11)
    font.setBold(True)
    p.setFont(font)
    p.drawText(
        0,
        left.height(),
        left.width(),
        label_h,
        int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
        left_label,
    )
    p.drawText(
        left.width() + gap,
        right.height(),
        right.width(),
        label_h,
        int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
        right_label,
    )
    p.end()
    return out


def paint_hold_original(original: QPixmap, avail: QSize) -> QPixmap:
    """Full original with a clear badge so hold never looks like result."""
    base = scale_plain(original, avail)
    out = QPixmap(base.size())
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.drawPixmap(0, 0, base)
    # badge
    badge = "原图"
    font = QFont()
    font.setPointSize(12)
    font.setBold(True)
    p.setFont(font)
    fm = p.fontMetrics()
    tw = fm.horizontalAdvance(badge) + 16
    th = fm.height() + 10
    x, y = 10, 10
    p.setBrush(QColor(0, 0, 0, 140))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(x, y, tw, th, 6, 6)
    p.setPen(QColor("#ffffff"))
    p.drawText(
        x,
        y,
        tw,
        th,
        int(Qt.AlignmentFlag.AlignCenter),
        badge,
    )
    p.end()
    return out


def make_checkerboard(
    size: QSize,
    cell: int = 12,
    color_a: str = "#e6e6e8",
    color_b: str = "#ffffff",
) -> QPixmap:
    pm = QPixmap(size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    c1 = QColor(color_a)
    c2 = QColor(color_b)
    for y in range(0, size.height(), cell):
        for x in range(0, size.width(), cell):
            painter.fillRect(
                x,
                y,
                cell,
                cell,
                c1 if ((x // cell) + (y // cell)) % 2 == 0 else c2,
            )
    painter.end()
    return pm


class DropCanvas(QFrame):
    """
    Peel-like central canvas:
    - drag images in to process
    - drag result out as a PNG file
    """

    file_dropped = Signal(str)
    files_dropped = Signal(list)  # list[str]
    open_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropCanvas")
        self.setAcceptDrops(True)
        # Soft min — hard 420px forced bottom buttons into the canvas when short
        self.setMinimumSize(200, 160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._result_pixmap: Optional[QPixmap] = None
        self._original_pixmap: Optional[QPixmap] = None
        # layout: single result | side-by-side (left orig, right result)
        self._side_by_side = False
        # long-press / Space: None | "full" | "left" | "right"
        # full = single view show original; left/right = flip that pane only
        self._hold_side: Optional[str] = None
        self._drag_file: Optional[Path] = None
        self._busy = False
        self._status = "idle"  # idle | busy | result | error
        self._message = ""
        self._press_pos: Optional[QPoint] = None
        self._press_active = False
        self._drag_started = False
        self._checker: Tuple[str, str] = ("#e6e6e8", "#ffffff")
        self._dash_color = QColor("#34c759")
        self._long_press_ms = 180
        self._drag_threshold = 10
        self._long_press_timer = QTimer(self)
        self._long_press_timer.setSingleShot(True)
        self._long_press_timer.timeout.connect(self._on_long_press)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(28, 28, 28, 28)
        self._layout.setSpacing(10)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.emoji = QLabel("🥝")
        self.emoji.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.emoji.setObjectName("HeroEmoji")
        self.emoji.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.emoji.setAutoFillBackground(False)
        f = QFont()
        f.setPointSize(42)
        self.emoji.setFont(f)

        self.title = QLabel("Peel")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setObjectName("HeroTitle")
        self.title.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.title.setAutoFillBackground(False)

        self.hint = QLabel("拖入图片去背景\n或点击选择文件")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setObjectName("HeroHint")
        self.hint.setWordWrap(True)
        self.hint.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.hint.setAutoFillBackground(False)

        self.preview = FitPixmapLabel()
        self.preview.setObjectName("PreviewLabel")
        self.preview.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.preview.setAutoFillBackground(False)
        # Let DropCanvas receive long-press / drag (child would otherwise eat events)
        self.preview.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.preview.hide()

        self.drag_hint = QLabel("长按看原图 · 拖移可拖出结果")
        self.drag_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drag_hint.setObjectName("DragOutHint")
        self.drag_hint.setWordWrap(False)
        self.drag_hint.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.drag_hint.setAutoFillBackground(False)
        self.drag_hint.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.drag_hint.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.drag_hint.hide()

        # F09: single-preview only — 左右对照 button + long-press peek
        self.compare_bar = QWidget()
        self.compare_bar.setObjectName("CompareBar")
        self.compare_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        cmp_l = QHBoxLayout(self.compare_bar)
        cmp_l.setContentsMargins(0, 2, 0, 0)
        cmp_l.setSpacing(8)
        cmp_l.addStretch(1)
        self.btn_side_by_side = QPushButton("左右对照")
        self.btn_side_by_side.setObjectName("CompareBtn")
        self.btn_side_by_side.setCheckable(True)
        self.btn_side_by_side.setToolTip(
            "左原图 · 右结果。长按某一侧会在原位临时换成另一张，松开恢复。"
        )
        self.btn_side_by_side.toggled.connect(self._on_side_by_side_toggled)
        cmp_l.addWidget(self.btn_side_by_side)
        cmp_l.addStretch(1)
        self.compare_bar.hide()

        # Indices for stretch tuning: idle centers hero; result maximizes image
        self._idx_stretch_top = self._layout.count()
        self._layout.addStretch(1)
        self._layout.addWidget(self.emoji)
        self._layout.addWidget(self.title)
        self._layout.addWidget(self.hint)
        self._idx_preview = self._layout.count()
        self._layout.addWidget(self.preview, 1)
        self._layout.addWidget(self.compare_bar, 0)
        self._layout.addWidget(self.drag_hint, 0)
        self._idx_stretch_bot = self._layout.count()
        self._layout.addStretch(1)

    def _set_preview_fill_mode(self, fill: bool) -> None:
        """
        fill=True (result): image takes nearly all free height.
        fill=False (idle/busy): keep vertical centering via equal stretches.
        """
        if fill:
            self._layout.setContentsMargins(10, 8, 10, 8)
            self._layout.setSpacing(6)
            self._layout.setStretch(self._idx_stretch_top, 0)
            self._layout.setStretch(self._idx_preview, 1)
            self._layout.setStretch(self._idx_stretch_bot, 0)
        else:
            self._layout.setContentsMargins(28, 28, 28, 28)
            self._layout.setSpacing(10)
            self._layout.setStretch(self._idx_stretch_top, 1)
            self._layout.setStretch(self._idx_preview, 0)
            self._layout.setStretch(self._idx_stretch_bot, 1)

    def apply_theme_colors(
        self,
        *,
        checker_a: str,
        checker_b: str,
        accent_dash: str,
    ) -> None:
        self._checker = (checker_a, checker_b)
        self._dash_color = QColor(accent_dash)
        if self._result_pixmap is not None:
            self._update_preview_scaled()
        self.update()

    def _has_original(self) -> bool:
        return (
            self._original_pixmap is not None and not self._original_pixmap.isNull()
        )

    def _reset_compare_state(self) -> None:
        self._long_press_timer.stop()
        self._side_by_side = False
        self._hold_side = None
        self._press_active = False
        self._drag_started = False
        self._press_pos = None
        self.btn_side_by_side.blockSignals(True)
        self.btn_side_by_side.setChecked(False)
        self.btn_side_by_side.blockSignals(False)

    def set_busy(self, busy: bool, message: str = "正在去除背景…") -> None:
        self._busy = busy
        if busy:
            self._status = "busy"
            self._message = message
            self._reset_compare_state()
            self._set_preview_fill_mode(False)
            self.hint.setProperty("errorState", False)
            self.hint.style().unpolish(self.hint)
            self.hint.style().polish(self.hint)
            self.emoji.show()
            self.title.show()
            self.hint.setText(message)
            self.hint.show()
            self.preview.hide()
            self.compare_bar.hide()
            self.drag_hint.hide()
            self.setCursor(Qt.CursorShape.BusyCursor)
            self.setEnabled(True)
        else:
            if self._status != "result":
                self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_idle(self) -> None:
        self._busy = False
        self._status = "idle"
        self._result_pixmap = None
        self._original_pixmap = None
        self._drag_file = None
        self._reset_compare_state()
        self._set_preview_fill_mode(False)
        self.hint.setProperty("errorState", False)
        self.hint.style().unpolish(self.hint)
        self.hint.style().polish(self.hint)
        self.emoji.show()
        self.title.show()
        self.hint.setText("拖入图片去背景\n或点击选择文件")
        self.hint.show()
        self.preview.clear()
        self.preview.hide()
        self.compare_bar.hide()
        self.drag_hint.hide()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update()

    def set_error(self, message: str) -> None:
        self._busy = False
        self._status = "error"
        self._message = message
        self._reset_compare_state()
        self._set_preview_fill_mode(False)
        self.hint.setProperty("errorState", True)
        self.hint.style().unpolish(self.hint)
        self.hint.style().polish(self.hint)
        self.emoji.show()
        self.title.show()
        display = message.strip()
        if len(display) > 280:
            display = display[:277] + "…"
        self.hint.setText(f"出错了\n{display}\n\n拖入或点击重试")
        self.hint.show()
        self.preview.hide()
        self.compare_bar.hide()
        self.drag_hint.hide()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_result(
        self,
        pixmap: QPixmap,
        drag_file: Path,
        *,
        original: Optional[QPixmap] = None,
    ) -> None:
        self._busy = False
        self._status = "result"
        self._result_pixmap = pixmap
        self._original_pixmap = original
        self._drag_file = Path(drag_file)
        self._hold_side = None
        self._press_active = False
        self._drag_started = False
        self._long_press_timer.stop()
        # keep side_by_side preference across re-render of same session item
        self.hint.setProperty("errorState", False)
        self.hint.style().unpolish(self.hint)
        self.hint.style().polish(self.hint)
        self.emoji.hide()
        self.title.hide()
        self.hint.hide()
        # Maximize image: drop equal top/bottom stretch that was centering idle hero
        self._set_preview_fill_mode(True)
        self.preview.show()
        has_orig = original is not None and not original.isNull()
        if not has_orig:
            self._side_by_side = False
            self.btn_side_by_side.blockSignals(True)
            self.btn_side_by_side.setChecked(False)
            self.btn_side_by_side.blockSignals(False)
        self.compare_bar.setVisible(has_orig)
        self.btn_side_by_side.setEnabled(has_orig)
        self.btn_side_by_side.blockSignals(True)
        self.btn_side_by_side.setChecked(self._side_by_side and has_orig)
        self.btn_side_by_side.blockSignals(False)
        if has_orig:
            self.drag_hint.setText("长按对照 · 拖出结果")
            self.drag_hint.setToolTip(
                "长按/空格看原图；并排时长按一侧原位切换；拖移可拖出结果"
            )
        else:
            self.drag_hint.setText("拖移可拖出结果")
            self.drag_hint.setToolTip("按住结果可拖出到文件夹 / 其他应用")
        self.drag_hint.show()
        self._update_preview_scaled()
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.update()

    def set_hold_peek(self, on: bool) -> None:
        """Space hold: single → full original; side-by-side → flip result (right)."""
        if self._status != "result" or not self._has_original():
            return
        if on:
            side = "right" if self._side_by_side else "full"
            if self._hold_side == side:
                return
            self._hold_side = side
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            if self._hold_side is None:
                return
            self._hold_side = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._update_preview_scaled()

    def _on_side_by_side_toggled(self, checked: bool) -> None:
        if checked and not self._has_original():
            self.btn_side_by_side.blockSignals(True)
            self.btn_side_by_side.setChecked(False)
            self.btn_side_by_side.blockSignals(False)
            return
        self._side_by_side = bool(checked)
        self._hold_side = None
        self._update_preview_scaled()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._result_pixmap is not None:
            self._update_preview_scaled()

    def _hit_compare_side(self, widget_pos: QPoint) -> str:
        """Which pane under press: left | right | full (single mode)."""
        if not self._side_by_side:
            return "full"
        # Map canvas → preview label → centered pixmap
        pl = self.preview.mapFrom(self, widget_pos)
        pm = self.preview.pixmap()
        if pm is None or pm.isNull():
            return "right"
        avail = self.preview.size()
        ox = max(0, (avail.width() - pm.width()) // 2)
        oy = max(0, (avail.height() - pm.height()) // 2)
        x = pl.x() - ox
        y = pl.y() - oy
        if x < 0 or y < 0 or x >= pm.width() or y >= pm.height():
            # outside image: default by horizontal center of preview
            return "left" if pl.x() < avail.width() / 2 else "right"
        # composite is left | gap | right — half-split is good enough
        return "left" if x < pm.width() / 2 else "right"

    def _update_preview_scaled(self) -> None:
        if self._result_pixmap is None:
            return
        avail = self.preview.size()
        if avail.width() < 40 or avail.height() < 40:
            # Use almost full canvas; chrome is only a slim strip at bottom
            avail = QSize(
                max(self.width() - 20, 200),
                max(self.height() - 56, 200),
            )

        # Single view: hold → full original
        if self._hold_side == "full" and self._has_original():
            assert self._original_pixmap is not None
            self.preview.setPixmap(paint_hold_original(self._original_pixmap, avail))
            return

        if self._side_by_side and self._has_original():
            assert self._original_pixmap is not None
            flip_l = self._hold_side == "left"
            flip_r = self._hold_side == "right"
            self.preview.setPixmap(
                compose_side_by_side(
                    self._original_pixmap,
                    self._result_pixmap,
                    avail,
                    self._checker[0],
                    self._checker[1],
                    flip_left=flip_l,
                    flip_right=flip_r,
                )
            )
            return

        # Single result (not holding)
        self.preview.setPixmap(
            scale_with_checker(
                self._result_pixmap,
                avail,
                self._checker[0],
                self._checker[1],
            )
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self.property("dragOver"):
            painter = QPainter(self)
            pen = QPen(self._dash_color, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.drawRoundedRect(self.rect().adjusted(8, 8, -8, -8), 20, 20)
            painter.end()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if self._busy or should_ignore_drop(event.mimeData()):
            event.ignore()
            return
        if paths_from_mime(event.mimeData()):
            self.setProperty("dragOver", True)
            self.style().unpolish(self)
            self.style().polish(self)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        if self._busy or should_ignore_drop(event.mimeData()):
            event.ignore()
            return
        if paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)
        if self._busy or should_ignore_drop(event.mimeData()):
            event.ignore()
            return
        paths = paths_from_mime(event.mimeData())
        if paths:
            event.acceptProposedAction()
            strs = [str(p) for p in paths]
            self.files_dropped.emit(strs)
            self.file_dropped.emit(strs[0])
        else:
            event.ignore()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self._press_active = True
            self._drag_started = False
            if (
                self._status == "result"
                and self._has_original()
                and not self._busy
            ):
                self._long_press_timer.start(self._long_press_ms)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (
            self._status == "result"
            and self._press_active
            and self._press_pos is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and not self._drag_started
        ):
            dist = (event.position().toPoint() - self._press_pos).manhattanLength()
            if dist >= self._drag_threshold:
                # movement wins over long-press peek → drag-out result
                self._long_press_timer.stop()
                if self._hold_side is not None:
                    self._hold_side = None
                    self._update_preview_scaled()
                if self._drag_file and self._drag_file.is_file():
                    self._drag_started = True
                    self._press_active = False
                    self._start_drag_out()
                    self._press_pos = None
                    return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._long_press_timer.stop()
            was_peek = self._hold_side is not None
            if self._hold_side is not None:
                self._hold_side = None
                self._update_preview_scaled()
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            if (
                self._press_active
                and not self._drag_started
                and not was_peek
                and self._press_pos is not None
                and not self._busy
            ):
                if (
                    event.position().toPoint() - self._press_pos
                ).manhattanLength() < self._drag_threshold:
                    if self._status != "result":
                        self.open_clicked.emit()
            self._press_active = False
            self._drag_started = False
            self._press_pos = None
        super().mouseReleaseEvent(event)

    def _on_long_press(self) -> None:
        if not self._press_active or self._drag_started:
            return
        if self._status != "result" or not self._has_original():
            return
        pos = self._press_pos or QPoint(0, 0)
        self._hold_side = self._hit_compare_side(pos)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._update_preview_scaled()

    def _start_drag_out(self) -> None:
        if not self._drag_file or not self._drag_file.is_file():
            return
        drag = QDrag(self)
        mime = QMimeData()
        url = QUrl.fromLocalFile(str(self._drag_file.resolve()))
        mime.setUrls([url])
        mime.setText(str(self._drag_file.resolve()))
        # Custom type so drop-back into Peel is ignored (Explorer still gets file URL)
        mime.setData(PEEL_INTERNAL_MIME, b"1")
        drag.setMimeData(mime)
        if self._result_pixmap and not self._result_pixmap.isNull():
            thumb = self._result_pixmap.scaled(
                128,
                128,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            drag.setPixmap(thumb)
            drag.setHotSpot(QPoint(thumb.width() // 2, thumb.height() // 2))
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        begin_internal_drag_out()
        try:
            drag.exec(Qt.DropAction.CopyAction)
        finally:
            end_internal_drag_out()
        if self._status == "result":
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
