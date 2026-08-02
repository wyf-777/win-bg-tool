"""A focused selection-based repair dialog for background-removal results."""

from __future__ import annotations

from typing import Optional

from PIL import Image
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.services.mask_edit import (
    BrushSelection,
    LassoSelection,
    MaskEditHistory,
    Selection,
    apply_mask_edit,
)
from app.ui.widgets import MagneticDoneButton, ShakeBackButton, pil_to_qpixmap


class SelectionCanvas(QWidget):
    """Image viewport that records a selection in image coordinates."""

    selection_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(480, 320)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pixmap: Optional[QPixmap] = None
        self._original_pixmap: Optional[QPixmap] = None
        self._overlay_opacity = 0.38
        self._mode = "lasso"
        self._lasso: list[QPointF] = []
        self._polygon: list[QPointF] = []
        self._polygon_hover: Optional[QPointF] = None
        self._polygon_closed = False
        self._brush: list[QPointF] = []
        self._brush_radius = 16.0
        self._brush_selection_radius: Optional[float] = None
        self._drawing = False

    def set_images(self, original: Image.Image, result: Image.Image) -> None:
        if original.size != result.size:
            raise ValueError("original and result images must have the same size")
        self._original_pixmap = pil_to_qpixmap(original)
        self.set_image(result)

    def set_image(self, image: Image.Image) -> None:
        self._pixmap = pil_to_qpixmap(image)
        self.update()

    def set_overlay_opacity(self, percent: int) -> None:
        self._overlay_opacity = max(0.0, min(1.0, int(percent) / 100))
        self.update()

    def set_mode(self, mode: str) -> None:
        if mode not in {"lasso", "polygon", "brush"}:
            raise ValueError(f"unsupported selection mode: {mode}")
        if mode != self._mode:
            self._mode = mode
            self.clear_selection()

    def set_brush_diameter(self, diameter: int) -> None:
        self._brush_radius = max(1.0, float(diameter) / 2)
        if self._mode == "brush":
            self.update()

    def clear_selection(self) -> None:
        had_selection = self.selection() is not None or self.has_draft_selection
        self._lasso.clear()
        self._polygon.clear()
        self._polygon_hover = None
        self._polygon_closed = False
        self._brush.clear()
        self._brush_selection_radius = None
        self._drawing = False
        self.update()
        if had_selection:
            self.selection_changed.emit(False)

    @property
    def has_draft_selection(self) -> bool:
        return bool(self._polygon) and not self._polygon_closed

    @property
    def is_selecting(self) -> bool:
        return self._drawing or self.has_draft_selection

    def selection(self) -> Optional[Selection]:
        if self._mode == "lasso":
            if len(self._lasso) < 3:
                return None
            return LassoSelection(
                tuple((point.x(), point.y()) for point in self._lasso)
            )
        if self._mode == "polygon":
            if not self._polygon_closed or len(self._polygon) < 3:
                return None
            return LassoSelection(
                tuple((point.x(), point.y()) for point in self._polygon)
            )
        if not self._brush:
            return None
        return BrushSelection(
            tuple((point.x(), point.y()) for point in self._brush),
            self._brush_selection_radius or self._brush_radius,
        )

    def _image_rect(self):
        if self._pixmap is None or self._pixmap.isNull():
            return None
        size = self._pixmap.size().scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio
        )
        x = (self.width() - size.width()) / 2
        y = (self.height() - size.height()) / 2
        return x, y, size.width(), size.height()

    def _to_image(self, point: QPointF) -> Optional[QPointF]:
        rect = self._image_rect()
        if rect is None or self._pixmap is None:
            return None
        x, y, width, height = rect
        if not (x <= point.x() <= x + width and y <= point.y() <= y + height):
            return None
        image_x = (point.x() - x) * self._pixmap.width() / width
        image_y = (point.y() - y) * self._pixmap.height() / height
        return QPointF(image_x, image_y)

    def _to_view(self, point: QPointF) -> QPointF:
        rect = self._image_rect()
        assert rect is not None and self._pixmap is not None
        x, y, width, height = rect
        return QPointF(
            x + point.x() * width / self._pixmap.width(),
            y + point.y() * height / self._pixmap.height(),
        )

    def _selection_path(self) -> Optional[QPainterPath]:
        if self._mode == "polygon" and self._polygon:
            path = QPainterPath()
            points = [self._to_view(point) for point in self._polygon]
            path.moveTo(points[0])
            for point in points[1:]:
                path.lineTo(point)
            if self._polygon_closed:
                path.closeSubpath()
            elif self._polygon_hover is not None:
                path.lineTo(self._to_view(self._polygon_hover))
            return path

        selection = self.selection()
        if selection is None:
            return None
        path = QPainterPath()
        if isinstance(selection, LassoSelection):
            points = [self._to_view(QPointF(x, y)) for x, y in selection.points]
            path.moveTo(points[0])
            for point in points[1:]:
                path.lineTo(point)
            path.closeSubpath()
        else:
            points = [self._to_view(QPointF(x, y)) for x, y in selection.points]
            path.moveTo(points[0])
            for point in points[1:]:
                path.lineTo(point)
        return path

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#202124"))
        rect = self._image_rect()
        if rect is None or self._pixmap is None:
            painter.end()
            return
        x, y, width, height = rect
        tile = 12
        for row in range(int(y), int(y + height), tile):
            for col in range(int(x), int(x + width), tile):
                light = ((row - int(y)) // tile + (col - int(x)) // tile) % 2 == 0
                painter.fillRect(col, row, tile, tile, QColor("#f2f2f3" if light else "#d6d6d8"))
        if self._original_pixmap is not None:
            painter.setOpacity(self._overlay_opacity)
            painter.drawPixmap(
                int(x), int(y), int(width), int(height), self._original_pixmap
            )
            painter.setOpacity(1.0)
        painter.drawPixmap(int(x), int(y), int(width), int(height), self._pixmap)
        path = self._selection_path()
        if path is not None:
            selection = self.selection()
            if self._mode == "polygon" and not self._polygon_closed:
                painter.setPen(QPen(QColor("#34c759"), 2))
                painter.drawPath(path)
                painter.setBrush(QColor(52, 199, 89, 170))
                painter.setPen(Qt.PenStyle.NoPen)
                for point in self._polygon:
                    painter.drawEllipse(self._to_view(point), 3, 3)
            elif isinstance(selection, BrushSelection):
                brush_width = max(
                    2.0, selection.radius * 2 * width / self._pixmap.width()
                )
                pen = QPen(QColor(52, 199, 89, 112), brush_width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.drawPath(path)
                first = self._to_view(QPointF(*selection.points[0]))
                painter.setBrush(QColor(52, 199, 89, 112))
                painter.drawEllipse(first, brush_width / 2, brush_width / 2)
            else:
                painter.fillPath(path, QColor(52, 199, 89, 58))
                painter.setPen(QPen(QColor("#34c759"), 2))
                painter.drawPath(path)
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = self._to_image(event.position())
        if point is None:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if self._mode == "polygon":
            if self._polygon_closed:
                self.clear_selection()
            if (
                len(self._polygon) >= 3
                and (event.position() - self._to_view(self._polygon[0])).manhattanLength()
                <= 12
            ):
                self._polygon_closed = True
                self._polygon_hover = None
            else:
                self._polygon.append(point)
                self._polygon_hover = point
            self.update()
            self.selection_changed.emit(self.selection() is not None)
            event.accept()
            return
        self._drawing = True
        if self._mode == "lasso":
            self._lasso = [point]
        else:
            self._brush = [point]
            self._brush_selection_radius = self._brush_radius
        self.update()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._mode == "polygon" and self._polygon and not self._polygon_closed:
            point = self._to_image(event.position())
            if point != self._polygon_hover:
                self._polygon_hover = point
                self.update()
            event.accept()
            return
        if not self._drawing or not event.buttons() & Qt.MouseButton.LeftButton:
            return
        point = self._to_image(event.position())
        if point is None:
            return
        if self._mode == "lasso" and (
            not self._lasso or (point - self._lasso[-1]).manhattanLength() >= 1
        ):
            self._lasso.append(point)
        elif self._mode == "brush" and (
            not self._brush or (point - self._brush[-1]).manhattanLength() >= 1
        ):
            self._brush.append(point)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or not self._drawing:
            return
        self._drawing = False
        valid = self.selection() is not None
        self.update()
        self.selection_changed.emit(valid)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if (
            self._mode == "polygon"
            and event.button() == Qt.MouseButton.LeftButton
            and len(self._polygon) >= 3
        ):
            self._polygon_closed = True
            self._polygon_hover = None
            self.update()
            self.selection_changed.emit(True)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._mode == "polygon" and event.key() in {
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        }:
            if len(self._polygon) >= 3:
                self._polygon_closed = True
                self._polygon_hover = None
                self.update()
                self.selection_changed.emit(True)
            event.accept()
            return
        if self._mode == "polygon" and event.key() == Qt.Key.Key_Backspace:
            if self._polygon and not self._polygon_closed:
                self._polygon.pop()
                self._polygon_hover = self._polygon[-1] if self._polygon else None
                self.update()
                self.selection_changed.emit(False)
            event.accept()
            return
        if self._mode == "polygon" and event.key() == Qt.Key.Key_Escape:
            self.clear_selection()
            event.accept()
            return
        super().keyPressEvent(event)


class MaskEditorDialog(QWidget):
    """Full-window repair page that only changes the alpha result on completion."""

    completed = Signal()
    cancelled = Signal()

    def __init__(
        self,
        original: Image.Image,
        result: Image.Image,
        title: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"修补 - {title}")
        self.setMinimumSize(720, 540)
        self._history = MaskEditHistory(original, result)
        self._last_edit: Optional[tuple[Image.Image, Selection, str]] = None
        self.edited_image: Optional[Image.Image] = None

        self.setObjectName("RepairPage")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.top_bar = QWidget()
        self.top_bar.setObjectName("RepairTopBar")
        header = QHBoxLayout(self.top_bar)
        header.setContentsMargins(16, 10, 16, 10)
        header.setSpacing(8)
        self.back_button = ShakeBackButton()
        self.back_button.clicked.connect(self.cancel_editing)
        self.title_label = QLabel(f"修补 · {title}")
        self.title_label.setObjectName("RepairTitle")
        self.title_label.setMinimumWidth(0)
        self.title_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.done_button = MagneticDoneButton()
        self.done_button.clicked.connect(self._done)
        header.addWidget(self.back_button, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.title_label, 1)
        header.addWidget(self.done_button, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(self.top_bar)

        content = QHBoxLayout()
        content.setContentsMargins(12, 12, 12, 12)
        content.setSpacing(12)

        self.canvas = SelectionCanvas()
        self.canvas.set_images(self._history.original, self._history.current)
        self.canvas.selection_changed.connect(self._on_selection_changed)

        self.sidebar = QScrollArea()
        self.sidebar.setObjectName("RepairSidebar")
        self.sidebar.setWidgetResizable(True)
        self.sidebar.setFrameShape(QScrollArea.Shape.NoFrame)
        self.sidebar.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.sidebar.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        # Wide enough for two equal history buttons + padding (global
        # QPushButton min-width is 88px; Repair* styles override to 0).
        self.sidebar.setFixedWidth(208)
        self.sidebar.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        self._sidebar_content = QWidget()
        self._sidebar_content.setObjectName("RepairSidebarContent")
        self._sidebar_layout = QVBoxLayout(self._sidebar_content)
        self._sidebar_layout.setContentsMargins(12, 14, 12, 14)
        self._sidebar_layout.setSpacing(6)

        def add_section(title: str, *, first: bool = False) -> None:
            if not first:
                self._sidebar_layout.addSpacing(8)
            label = QLabel(title)
            label.setObjectName("RepairSectionLabel")
            self._sidebar_layout.addWidget(label)

        def style_sidebar_button(button: QPushButton, object_name: str) -> None:
            button.setObjectName(object_name)
            button.setFixedHeight(34)
            button.setMinimumWidth(0)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )

        add_section("工具", first=True)
        self.lasso_button = QPushButton("自由套索")
        self.polygon_button = QPushButton("多边形套索")
        self.brush_button = QPushButton("画笔")
        for button in (
            self.lasso_button,
            self.polygon_button,
            self.brush_button,
        ):
            style_sidebar_button(button, "RepairToolBtn")
            button.setCheckable(True)
            self._sidebar_layout.addWidget(button)
        self.lasso_button.setChecked(True)
        self.lasso_button.clicked.connect(lambda: self._set_mode("lasso"))
        self.polygon_button.clicked.connect(lambda: self._set_mode("polygon"))
        self.brush_button.clicked.connect(lambda: self._set_mode("brush"))

        self.brush_options = QWidget()
        self.brush_options.setObjectName("RepairSliderBlock")
        brush_layout = QVBoxLayout(self.brush_options)
        brush_layout.setContentsMargins(2, 4, 2, 2)
        brush_layout.setSpacing(4)
        self.brush_label = QLabel("画笔 32 px")
        self.brush_label.setObjectName("RepairSliderLabel")
        self.brush_size = QSlider(Qt.Orientation.Horizontal)
        self._style_sidebar_slider(self.brush_size)
        self.brush_size.setRange(4, 120)
        self.brush_size.setValue(32)
        self.brush_size.valueChanged.connect(self._set_brush_diameter)
        brush_layout.addWidget(self.brush_label)
        brush_layout.addWidget(self.brush_size)
        self.brush_options.hide()
        self._sidebar_layout.addWidget(self.brush_options)

        add_section("边缘")
        self.feather_label = QLabel("羽化 4 px")
        self.feather_label.setObjectName("RepairSliderLabel")
        self.feather = QSlider(Qt.Orientation.Horizontal)
        self._style_sidebar_slider(self.feather)
        self.feather.setRange(0, 24)
        self.feather.setValue(4)
        self.feather.valueChanged.connect(self._set_feather)
        self._sidebar_layout.addWidget(self.feather_label)
        self._sidebar_layout.addWidget(self.feather)

        add_section("查看")
        self.overlay_strength_label = QLabel("叠加 38%")
        self.overlay_strength_label.setObjectName("RepairSliderLabel")
        self.overlay_strength = QSlider(Qt.Orientation.Horizontal)
        self._style_sidebar_slider(self.overlay_strength)
        self.overlay_strength.setRange(0, 100)
        self.overlay_strength.setValue(38)
        self.overlay_strength.setToolTip("调节原图在叠加视图中的显示强度")
        self.overlay_strength.valueChanged.connect(self._set_overlay_opacity)
        self._sidebar_layout.addWidget(self.overlay_strength_label)
        self._sidebar_layout.addWidget(self.overlay_strength)

        add_section("历史")
        self.undo_button = QPushButton("撤销")
        self.redo_button = QPushButton("重做")
        for button in (self.undo_button, self.redo_button):
            style_sidebar_button(button, "RepairToolBtn")
        self.undo_button.clicked.connect(self._undo)
        self.redo_button.clicked.connect(self._redo)
        history_tools = QHBoxLayout()
        history_tools.setContentsMargins(0, 0, 0, 0)
        history_tools.setSpacing(8)
        history_tools.addWidget(self.undo_button, 1)
        history_tools.addWidget(self.redo_button, 1)
        self._sidebar_layout.addLayout(history_tools)

        add_section("操作")
        self.keep_button = QPushButton("保留选区")
        self.erase_button = QPushButton("删除选区")
        self.restore_button = QPushButton("恢复选区")
        self.keep_button.clicked.connect(lambda: self._apply("keep"))
        self.erase_button.clicked.connect(lambda: self._apply("erase"))
        self.restore_button.clicked.connect(lambda: self._apply("restore"))
        for button in (self.keep_button, self.erase_button, self.restore_button):
            style_sidebar_button(button, "RepairActionBtn")
            self._sidebar_layout.addWidget(button)
        self.clear_selection_button = QPushButton("清除选区")
        style_sidebar_button(self.clear_selection_button, "RepairClearBtn")
        self.clear_selection_button.clicked.connect(self.canvas.clear_selection)
        self._sidebar_layout.addWidget(self.clear_selection_button)
        self._sidebar_layout.addStretch(1)
        self.sidebar.setWidget(self._sidebar_content)

        content.addWidget(self.sidebar)
        content.addWidget(self.canvas, 1)
        root.addLayout(content, 1)
        self._refresh_controls()

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
        """Sync capsule back / done buttons with the app theme."""
        kwargs = dict(
            bg=bg,
            border=border,
            hover=hover,
            pressed=pressed,
            disabled_bg=disabled_bg,
            primary=primary,
            text=text,
            disabled_text=disabled_text,
        )
        if hasattr(self.back_button, "apply_theme_colors"):
            self.back_button.apply_theme_colors(**kwargs)
        if hasattr(self.done_button, "apply_theme_colors"):
            self.done_button.apply_theme_colors(**kwargs)

    @staticmethod
    def _style_sidebar_slider(slider: QSlider) -> None:
        """Strip native fill so only the thin groove/handle remain visible."""
        slider.setAutoFillBackground(False)
        slider.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _set_mode(self, mode: str) -> None:
        self.lasso_button.setChecked(mode == "lasso")
        self.polygon_button.setChecked(mode == "polygon")
        self.brush_button.setChecked(mode == "brush")
        self.brush_options.setVisible(mode == "brush")
        self.canvas.set_mode(mode)

    def _set_brush_diameter(self, diameter: int) -> None:
        self.brush_label.setText(f"画笔 {diameter} px")
        self.canvas.set_brush_diameter(diameter)

    def _set_overlay_opacity(self, percent: int) -> None:
        self.overlay_strength_label.setText(f"叠加 {percent}%")
        self.canvas.set_overlay_opacity(percent)

    def _set_feather(self, value: int) -> None:
        self.feather_label.setText(f"羽化 {value} px")
        if (
            self._last_edit is None
            or self.canvas.selection() is not None
            or self.canvas.is_selecting
        ):
            return
        before, selection, operation = self._last_edit
        self._history.replace_current(
            apply_mask_edit(
                self._history.original, before, selection, operation, value
            )
        )
        self.canvas.set_image(self._history.current)

    def _on_selection_changed(self, _has_selection: bool) -> None:
        self._refresh_controls()

    def _refresh_controls(self) -> None:
        has_selection = self.canvas.selection() is not None
        for button in (self.keep_button, self.erase_button, self.restore_button):
            button.setEnabled(has_selection)
        self.clear_selection_button.setEnabled(
            has_selection or self.canvas.has_draft_selection
        )
        self.undo_button.setEnabled(self._history.can_undo)
        self.redo_button.setEnabled(self._history.can_redo)

    def _apply(self, operation: str) -> None:
        selection = self.canvas.selection()
        if selection is None:
            return
        before = self._history.current.copy()
        self._history.apply(selection, operation, self.feather.value())
        self._last_edit = (before, selection, operation)
        self.canvas.set_image(self._history.current)
        self.canvas.clear_selection()
        self._refresh_controls()

    def _undo(self) -> None:
        self._last_edit = None
        self.canvas.set_image(self._history.undo())
        self.canvas.clear_selection()
        self._refresh_controls()

    def _redo(self) -> None:
        self._last_edit = None
        self.canvas.set_image(self._history.redo())
        self.canvas.clear_selection()
        self._refresh_controls()

    def _done(self) -> None:
        self.edited_image = self._history.current.copy()
        self.completed.emit()

    def cancel_editing(self) -> None:
        self.cancelled.emit()
