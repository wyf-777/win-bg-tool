from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import (
    Qt,
    Signal,
    QByteArray,
    QEvent,
    QMimeData,
    QRectF,
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
from PySide6.QtSvg import QSvgRenderer
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


# User-provided paintbrush glyph (viewBox 0 0 1024 1024); fill color injected at paint.
_BRUSH_SVG_PATH = (
    "M432.7 621.3h66.8s61.4-1.4 89.5 47.4c21.7 37.5 33.7 74.6 39.2 94.4 "
    "6 27.6 15 53.2 23.3 67.6 22.3 38.6 71.7 51.9 110.3 29.6 38.6-22.3 "
    "51.9-71.7 29.6-110.3-8.3-14.4-26-35-47-54-14.4-14.7-40.5-43.6-62.2-81.1"
    "-28.1-48.9 3.8-101.3 3.8-101.3l33.4-57.8c7.1-15.3 7-33.8-2.1-49.6l-47.9"
    "-83-326.5 188.4 47.9 83a53.98 53.98 0 0 0 41.9 26.7z m262.6-177.8L663 "
    "499.6c-1.6 2.7-39.8 66.8-4 128.7 22.1 38.2 48.2 68.2 66.3 86.6l0.5 0.6 "
    "0.6 0.5c22.2 20.1 36.4 38.2 41.7 47.5 14.8 25.7 6 58.7-19.7 73.5-25.7 "
    "14.8-58.7 6-73.5-19.7-5.4-9.3-14-30.6-20.3-59.9l-0.2-0.8-0.2-0.7c-6.9"
    "-24.8-19.8-62.4-41.8-100.7-35.7-61.9-110.3-60.9-112.8-60.8h-65.4c-8.5"
    "-1.1-15.7-5.8-20-13.2l-7.6-13.1 279.8-161.5 7.6 13.1c4.2 7.3 4.7 16 "
    "1.3 23.8z m-35.9-83.6l13.5 23.3-279.8 161.6-13.5-23.3 279.8-161.6zM655.8 "
    "299.9l-54.5-94.4c-30.2-50.6-95.5-67.6-146.6-38.1l-23.2 13.4 37.8 68c"
    "-51.7-41.5-122.8-16.5-201 26.2l-46.6 26.9 107.7 186.5m139-297.9c38.1"
    "-21.9 87.3-9 109.6 28.4l41.1 71.1-69.9 40.4-80.8-139.9z m-129.1 261l"
    "-80.8-139.9 23.3-13.5c124.7-78.5 185.3-25.8 242.3 46.6L339.3 451.5z"
)

# User-provided reply/back arrow (viewBox 0 0 1024 1024).
_BACK_SVG_PATH = (
    "M458.33488356 820.35259846c-10.72530828 0-21.45061498-2.68132747"
    "-29.49459578-10.72530828l-319.0779052-265.45136692c-10.72530828"
    "-10.72530828-16.08796163-21.45061498-16.08796163-32.17592326 0"
    "-10.72530828 5.36265335-21.45061498 10.72530671-29.4945958l324.44056012"
    "-270.81402186c5.36265335-5.36265335 16.08796163-10.72530828 26.81326988"
    "-10.72530671s21.45061498 5.36265335 29.49459579 10.72530671l8.04398084"
    " 8.04398081V377.9336536h367.34179008c29.4945958 0 53.62653826 24.13194244"
    " 53.62653981 53.62653825v160.8796163c0 32.17592326-21.45061498"
    " 53.62653826-53.62653981 53.62653825H495.87346173v155.51696297l-8.0439808"
    " 8.04398081c-8.04398081 8.04398081-18.76928909 10.72530828-29.49459737"
    " 10.72530828z m5.36265493-50.94521235zM155.34494 512L442.24692193"
    " 750.63809701V592.43980815h420.96832989v-160.8796163H442.24692193v"
    "-158.19828886L155.34494 512z m311.03392437-260.08871357c0 2.68132747"
    " 0 0 0 0z"
)


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

    def __init__(
        self,
        kind: str,
        parent: Optional[QWidget] = None,
        *,
        size: int = 16,
    ) -> None:
        super().__init__(parent)
        self._kind = kind  # "settings" | "arrow" | "arrow_left" | "broom" | "brush"
        self._opacity = 1.0
        self._rotation = 0.0  # degrees
        self._color_override: Optional[QColor] = None
        self.setObjectName("SlideSettingsIcon")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        _make_icon_surface_transparent(self)
        side = max(12, int(size))
        self.setFixedSize(side, side)

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

    def _paint_user_svg(
        self,
        p: QPainter,
        color: QColor,
        path_d: str,
        *,
        stroke_w: float = 0.0,
        pad: float = 1.0,
    ) -> None:
        """Render a filled 1024×1024 SVG path, recolored, with DPR oversampling."""
        fill = color.name(QColor.NameFormat.HexRgb)
        if stroke_w > 0:
            path_attrs = (
                f'fill="{fill}" stroke="{fill}" stroke-width="{stroke_w}" '
                f'stroke-linejoin="round" stroke-linecap="round"'
            )
        else:
            path_attrs = f'fill="{fill}"'
        svg = (
            '<svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg">'
            f'<path d="{path_d}" {path_attrs}/>'
            "</svg>"
        )
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        side = max(self.width(), self.height(), 1)
        dpr = max(1.0, float(self.devicePixelRatioF()))
        scale = max(2.0, dpr)
        pm = QPixmap(int(side * scale), int(side * scale))
        pm.fill(QColor(0, 0, 0, 0))
        pm.setDevicePixelRatio(scale)
        sp = QPainter(pm)
        sp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        sp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        renderer.render(sp, QRectF(pad, pad, side - 2 * pad, side - 2 * pad))
        sp.end()
        p.drawPixmap(0, 0, pm)

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

        if self._kind == "check":
            # ✓ check mark
            p.drawLine(QPointF(cx - 4.2, cy + 0.2), QPointF(cx - 1.0, cy + 3.6))
            p.drawLine(QPointF(cx - 1.0, cy + 3.6), QPointF(cx + 5.0, cy - 3.4))
            return

        if self._kind == "arrow_back":
            # User SVG reply/back arrow — filled, theme-colored
            self._paint_user_svg(p, color, _BACK_SVG_PATH, stroke_w=28, pad=1.0)
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

        if self._kind == "brush":
            # User SVG paintbrush — filled glyph, recolored to theme text.
            self._paint_user_svg(p, color, _BRUSH_SVG_PATH, stroke_w=40, pad=1.0)
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

        self.setToolTip("返回主界面（Esc 同样可返回）")
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


class ShakeBackButton(QFrame):
    """
    Repair-page「返回」per text.md ShakeButton:
      whileHover scale 1.02 / whileTap 0.96
      icon on hover: y [0,-2,0,-2,0], rotate [0,-10,10,-10,0], duration 0.4s
    """

    clicked = Signal()

    _BASE_H = 36
    _ICON = 18
    _PAD_X = 22
    _GAP = 8  # ml-2.5
    _DUR_SHAKE = 400  # text.md transition.duration 0.4
    _Y_KEYS = (0.0, -2.0, 0.0, -2.0, 0.0)
    _ROT_KEYS = (0.0, -10.0, 10.0, -10.0, 0.0)

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
        self._shake_t = 0.0
        self._icon_y = 0.0
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

        self.icon = _LineIcon("arrow_back", self.icon_slot, size=self._ICON)
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
        self._anim.setEndValue(1.0)
        self._anim.setDuration(self._DUR_SHAKE)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._anim.valueChanged.connect(self._on_shake)
        self._anim.finished.connect(self._on_shake_finished)

        self.setToolTip("返回，放弃本次修补")
        self._cache_caption_width()
        base = self._base_size()
        self._host_w = int(round(base.width() * 1.06)) + 2
        self._host_h = int(round(base.height() * 1.06)) + 2
        self.setFixedSize(self._host_w, self._host_h)
        self._apply_layout()

    @staticmethod
    def _keyframes(t: float, values: tuple[float, ...]) -> float:
        """Evenly spaced keyframe lerp for t∈[0,1]."""
        if not values:
            return 0.0
        t = max(0.0, min(1.0, float(t)))
        if len(values) == 1 or t <= 0.0:
            return values[0]
        if t >= 1.0:
            return values[-1]
        n = len(values) - 1
        x = t * n
        i = int(x)
        if i >= n:
            return values[-1]
        f = x - i
        return values[i] + (values[i + 1] - values[i]) * f

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

    def _on_shake(self, value) -> None:
        self._shake_t = float(value)
        self._icon_y = self._keyframes(self._shake_t, self._Y_KEYS)
        self.icon.set_rotation(self._keyframes(self._shake_t, self._ROT_KEYS))
        self._apply_layout()

    def _on_shake_finished(self) -> None:
        # text.md plays once per hover enter; settle at rest
        self._shake_t = 0.0
        self._icon_y = 0.0
        self.icon.set_rotation(0.0)
        self._apply_layout()

    def _play_shake(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(self._DUR_SHAKE)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._anim.start()

    def _stop_shake(self) -> None:
        self._anim.stop()
        self._shake_t = 0.0
        self._icon_y = 0.0
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
        # icon y-bounce within slot (text.md y: [0,-2,0,-2,0])
        iy = int(round(self._icon_y))
        self.icon_slot.setGeometry(
            int(round(start)), row_y + iy, self._ICON, self._ICON
        )
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
            self._stop_shake()
        self._sync_shell()
        self._apply_fg_colors()

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802
        super().enterEvent(event)
        if self._enabled:
            self._hovered = True
            self._sync_shell()
            self._apply_layout()
            self._play_shake()

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self._hovered = False
        self._pressed = False
        self._sync_shell()
        self._stop_shake()

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


class MagneticDoneButton(QFrame):
    """
    Repair-page「完成」— strict port of text.md MagneticButton:

      handleMouseMove:
        x = clientX - left - width/2   # relative to *button* center
        y = clientY - top  - height/2
        mouseCoords = { x: x * 0.35, y: y * 0.35 }

      animate x/y → mouseCoords while hovered, else 0
      whileTap scale 0.96  (no whileHover scale)
      h-[36px] px-6 (24)  icon w-4 (16)  mr-2.5 (10)  text 13px
      transition-colors duration-150
    """

    clicked = Signal()

    # ── text.md layout constants ──────────────────────────
    _BASE_H = 36          # h-[36px]
    _ICON = 16            # w-4 h-4
    _PAD_X = 24           # px-6
    _GAP = 10             # mr-2.5
    _MAGNET = 0.35        # x * 0.35
    _TAP_SCALE = 0.96     # whileTap
    # framer-motion default spring-ish follow (no explicit transition in text.md)
    _SPRING_K = 0.42      # position blend per tick toward target
    _TICK_MS = 16
    # transition-colors duration-150 — shell paint is instant; kept for docs parity
    _COLOR_MS = 150

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SlideSettingsHost")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._hovered = False
        self._pressed = False
        self._enabled = True
        # current translated offset (animated)
        self._mag_x = 0.0
        self._mag_y = 0.0
        # target from last mouse sample (text.md mouseCoords)
        self._target_x = 0.0
        self._target_y = 0.0
        self._caption_w = 28
        self._fg = "#ffffff"
        self._fg_disabled = "#a1a1a6"

        self.shell = _CapsuleShell(self)
        self.shell.set_fill_primary(True)

        self.icon_slot = QWidget(self.shell)
        self.icon_slot.setObjectName("SlideSettingsSlot")
        self.icon_slot.setFixedSize(self._ICON, self._ICON)
        self.icon_slot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        _make_icon_surface_transparent(self.icon_slot)

        self.icon = _LineIcon("check", self.icon_slot, size=self._ICON)
        self.icon.setGeometry(0, 0, self._ICON, self._ICON)
        self.icon.set_opacity(1.0)
        self.icon.set_color_override(QColor(self._fg))

        self.caption = QLabel("完成", self.shell)
        self.caption.setObjectName("SlideSettingsText")
        self.caption.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self.caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        # text.md text-[13px]
        cap_font = self.caption.font()
        cap_font.setPixelSize(13)
        self.caption.setFont(cap_font)

        self._spring_timer = QTimer(self)
        self._spring_timer.setInterval(self._TICK_MS)
        self._spring_timer.timeout.connect(self._tick_spring)

        self.setToolTip("应用修补并返回")
        self._cache_caption_width()
        self._rebuild_host_size()
        self._apply_fg_colors()
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
        del text  # text.md text-white on solid primary
        self.shell.apply_theme_colors(
            bg=bg,
            border=border,
            hover=hover,
            pressed=pressed,
            disabled_bg=disabled_bg,
            primary=primary,
        )
        self.shell.set_fill_primary(True)
        self._fg = "#ffffff"
        self._fg_disabled = disabled_text
        self._apply_fg_colors()

    def _apply_fg_colors(self) -> None:
        col = QColor(self._fg if self._enabled else self._fg_disabled)
        self.icon.set_color_override(col)
        pal = self.caption.palette()
        pal.setColor(QPalette.ColorRole.WindowText, col)
        pal.setColor(QPalette.ColorRole.Text, col)
        self.caption.setPalette(pal)
        self.caption.update()
        self.icon.update()

    def _cache_caption_width(self) -> None:
        self.caption.adjustSize()
        self._caption_w = max(self.caption.sizeHint().width(), 24)

    def _base_size(self) -> QSize:
        """Visual button size (text.md button rect — magnetic range base)."""
        w = self._PAD_X * 2 + self._ICON + self._GAP + self._caption_w
        return QSize(w, self._BASE_H)

    def _max_magnet_offset(self) -> tuple[float, float]:
        """Max |x*0.35| / |y*0.35| when cursor is at button edge."""
        base = self._base_size()
        return (
            (base.width() * 0.5) * self._MAGNET,
            (base.height() * 0.5) * self._MAGNET,
        )

    def _rebuild_host_size(self) -> None:
        base = self._base_size()
        max_x, max_y = self._max_magnet_offset()
        # Host only needs room for magnetic travel + whileTap shrink inset
        pad_x = int(math.ceil(max_x)) + 2
        pad_y = int(math.ceil(max_y)) + 2
        self._host_w = base.width() + 2 * pad_x
        self._host_h = base.height() + 2 * pad_y
        self.setFixedSize(self._host_w, self._host_h)

    def _scale_now(self) -> float:
        # text.md: only whileTap scale 0.96 — no whileHover scale
        if self._pressed and self._enabled:
            return self._TAP_SCALE
        return 1.0

    def _apply_layout(self) -> None:
        scale = self._scale_now()
        base = self._base_size()
        sw = max(1, int(round(base.width() * scale)))
        sh = max(1, int(round(base.height() * scale)))
        # Resting center of host + magnetic translate (text.md animate x/y)
        cx = self._host_w / 2.0 + self._mag_x
        cy = self._host_h / 2.0 + self._mag_y
        self.shell.setGeometry(
            int(round(cx - sw / 2.0)),
            int(round(cy - sh / 2.0)),
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

    def _ensure_spring(self) -> None:
        if not self._spring_timer.isActive():
            self._spring_timer.start()

    def _tick_spring(self) -> None:
        """Blend current offset toward target (framer animate spring feel)."""
        k = self._SPRING_K
        nx = self._mag_x + (self._target_x - self._mag_x) * k
        ny = self._mag_y + (self._target_y - self._mag_y) * k
        # Snap when close enough
        if abs(nx - self._target_x) < 0.08 and abs(ny - self._target_y) < 0.08:
            nx, ny = self._target_x, self._target_y
            if not self._hovered and abs(nx) < 0.08 and abs(ny) < 0.08:
                nx = ny = 0.0
                self._spring_timer.stop()
        if abs(nx - self._mag_x) < 0.02 and abs(ny - self._mag_y) < 0.02:
            if nx == self._target_x and ny == self._target_y:
                if not self._hovered:
                    self._spring_timer.stop()
                self._mag_x, self._mag_y = nx, ny
                self._apply_layout()
                return
        self._mag_x, self._mag_y = nx, ny
        self._apply_layout()

    def _set_target(self, tx: float, ty: float) -> None:
        max_x, max_y = self._max_magnet_offset()
        # Hard clamp to theoretical text.md range (± half-button * 0.35)
        tx = max(-max_x, min(max_x, tx))
        ty = max(-max_y, min(max_y, ty))
        self._target_x = tx
        self._target_y = ty
        self._ensure_spring()

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
            self._spring_timer.stop()
            self._target_x = self._target_y = 0.0
            self._mag_x = self._mag_y = 0.0
            self._apply_layout()
        self._sync_shell()
        self._apply_fg_colors()

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802
        super().enterEvent(event)
        if self._enabled:
            self._hovered = True
            self._sync_shell()
            self._update_magnet_from_pos(event.position())

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self._hovered = False
        self._pressed = False
        self._sync_shell()
        # text.md: setMouseCoords({ x: 0, y: 0 }) — animate back to rest
        self._set_target(0.0, 0.0)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._enabled and self._hovered:
            self._update_magnet_from_pos(event.position())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def _update_magnet_from_pos(self, pos) -> None:
        """
        text.md (relative to *button* rect, not expanded host):
          x = clientX - left - width/2
          y = clientY - top  - height/2
          mouseCoords = { x: x * 0.35, y: y * 0.35 }
        """
        base = self._base_size()
        # Button rests centered in host; map host pos → button-local
        btn_left = (self._host_w - base.width()) / 2.0
        btn_top = (self._host_h - base.height()) / 2.0
        # Cursor relative to button center (same formula as getBoundingClientRect)
        dx = float(pos.x()) - btn_left - base.width() / 2.0
        dy = float(pos.y()) - btn_top - base.height() / 2.0
        # While pointer is only tracked on host, clamp to button half-extents
        # so range never exceeds real button-edge * 0.35
        half_w = base.width() / 2.0
        half_h = base.height() / 2.0
        dx = max(-half_w, min(half_w, dx))
        dy = max(-half_h, min(half_h, dy))
        self._set_target(dx * self._MAGNET, dy * self._MAGNET)

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


class SlideRepairButton(QFrame):
    """
    Main-window「修补」: outline capsule + paintbrush icon.
    Same hover motion as「清除」: brush sweeps 0° → -45° → +45° → 0°.
    Scale 1.02 on hover / 0.96 on press.
    """

    clicked = Signal()

    _BASE_H = 36
    # Filled SVG brush needs more pixels than line icons (16) to stay legible
    _ICON = 22
    _PAD_X = 22
    _GAP = 8
    _DUR_SWEEP = 720

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
        self._sweep_t = 0.0
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

        self.icon = _LineIcon("brush", self.icon_slot, size=self._ICON)
        self.icon.setGeometry(0, 0, self._ICON, self._ICON)
        self.icon.set_opacity(1.0)
        self.icon.set_rotation(0.0)

        self.caption = QLabel("修补", self.shell)
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

        self.setToolTip("对当前结果做手动修补（圈选删除 / 恢复 / 保留）")
        self._cache_caption_width()
        base = self._base_size()
        self._host_w = int(round(base.width() * 1.06)) + 2
        self._host_h = int(round(base.height() * 1.06)) + 2
        self.setFixedSize(self._host_w, self._host_h)
        self._apply_layout()
        self.setEnabled(False)

    @staticmethod
    def _brush_angle(t: float) -> float:
        """Same sweep as clear broom: 0 → -45 → +45 → 0."""
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
        self.caption.setText(text or "修补")
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
        self.icon.set_rotation(self._brush_angle(self._sweep_t))
        self._apply_layout()

    def _on_sweep_finished(self) -> None:
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
