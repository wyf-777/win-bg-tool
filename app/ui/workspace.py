from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QSize, QMimeData, QUrl, QPoint, QTimer
from PySide6.QtGui import (
    QColor,
    QDrag,
    QDragEnterEvent,
    QDropEvent,
    QMouseEvent,
    QPainter,
    QPixmap,
    QShowEvent,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.engines.models_catalog import MODEL_CATALOG, is_model_downloaded
from app.services.image_io import load_preview_image
from app.session.models import ImageItem, ItemStatus
from app.ui.widgets import (
    PEEL_INTERNAL_MIME,
    DropCanvas,
    FitPixmapLabel,
    begin_internal_drag_out,
    compose_side_by_side,
    end_internal_drag_out,
    make_checkerboard,
    paint_hold_original,
    path_from_mime,
    paths_from_mime,
    pil_to_qpixmap,
    scale_with_checker,
    should_ignore_drop,
)


def _populate_reprocess_menu(
    menu: QMenu,
    *,
    can_reprocess: bool,
    on_pick_model,
) -> None:
    """Shared 「用已下载模型重抠」submenu for single canvas and multi tiles."""
    submenu = menu.addMenu("用已下载模型重抠")
    downloaded = [m for m in MODEL_CATALOG if is_model_downloaded(m.id)]
    if not downloaded:
        empty = submenu.addAction("（暂无已下载模型，请到设置下载）")
        empty.setEnabled(False)
        return
    if not can_reprocess:
        tip = submenu.addAction("仅可对「完成 / 失败」的图片重抠")
        tip.setEnabled(False)
        submenu.addSeparator()
    for info in downloaded:
        act = submenu.addAction(info.label)
        act.setEnabled(can_reprocess)
        act.setToolTip(info.skill or info.id)
        mid = info.id
        act.triggered.connect(lambda _checked=False, m=mid: on_pick_model(m))


class Workspace(QFrame):
    """
    Main content area:
    - empty / single: DropCanvas
    - multi: scrollable grid
    - lightbox overlay for multi view
    """

    paths_dropped = Signal(list)  # list[str]
    open_clicked = Signal()
    selection_changed = Signal()
    request_export_selected = Signal()
    request_export_all = Signal()
    # Multi-grid: re-run one item with a downloaded model
    reprocess_requested = Signal(str, str)  # item_id, model_id

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Workspace")
        self.setAcceptDrops(True)
        # Soft min so bottom action bar keeps room when window is short
        self.setMinimumSize(200, 160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._items: List[ImageItem] = []
        self._checker = ("#e6e6e8", "#ffffff")
        self._dash = QColor("#34c759")
        self._lightbox_index = -1

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # page 0: single / empty canvas
        self.canvas = DropCanvas()
        self.canvas.files_dropped.connect(self.paths_dropped.emit)
        self.canvas.open_clicked.connect(self.open_clicked.emit)
        self.canvas.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.canvas.customContextMenuRequested.connect(self._on_single_context_menu)
        self.stack.addWidget(self.canvas)

        # page 1: multi grid (toolbar moved to main bottom bar — avoid duplicate 导出)
        self.grid_page = QWidget()
        grid_layout = QVBoxLayout(self.grid_page)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setObjectName("GridScroll")

        self.grid_host = QWidget()
        self.grid_host.setObjectName("DropCanvas")
        self.grid_layout = QGridLayout(self.grid_host)
        self.grid_layout.setContentsMargins(16, 16, 16, 16)
        self.grid_layout.setSpacing(12)
        self.scroll.setWidget(self.grid_host)
        grid_layout.addWidget(self.scroll, 1)

        self.stack.addWidget(self.grid_page)

        # lightbox overlay (sibling on top via stack page 2)
        self.lightbox = Lightbox()
        self.lightbox.closed.connect(self._close_lightbox)
        self.lightbox.changed.connect(self._on_lightbox_nav)
        self.stack.addWidget(self.lightbox)

        self._tile_widgets: dict[str, _GridTile] = {}

    def apply_theme_colors(self, *, checker_a: str, checker_b: str, accent_dash: str) -> None:
        self._checker = (checker_a, checker_b)
        self._dash = QColor(accent_dash)
        self.canvas.apply_theme_colors(
            checker_a=checker_a, checker_b=checker_b, accent_dash=accent_dash
        )
        self.lightbox.apply_theme_colors(checker_a=checker_a, checker_b=checker_b)
        for tile in self._tile_widgets.values():
            tile.set_checker(checker_a, checker_b)

    def set_hold_peek(self, on: bool) -> None:
        """Space hold → original on single canvas or lightbox (not grid)."""
        cur = self.stack.currentWidget()
        if cur is self.canvas:
            self.canvas.set_hold_peek(on)
        elif cur is self.lightbox:
            self.lightbox.set_hold_peek(on)

    def set_items(self, items: List[ImageItem]) -> None:
        self._items = list(items)
        n = len(self._items)
        if self._lightbox_index >= 0 and n >= 2:
            # keep lightbox if still multi
            if self._lightbox_index >= n:
                self._lightbox_index = n - 1
            self._show_lightbox(self._lightbox_index)
            return

        self._lightbox_index = -1
        if n == 0:
            self.stack.setCurrentWidget(self.canvas)
            self.canvas.set_idle()
        elif n == 1:
            self.stack.setCurrentWidget(self.canvas)
            self._render_single(self._items[0])
        else:
            self.stack.setCurrentWidget(self.grid_page)
            self._rebuild_grid()

    def update_item(self, item: ImageItem) -> None:
        # refresh single or one tile
        if len(self._items) == 1 and self._items[0].id == item.id:
            self._render_single(item)
            return
        tile = self._tile_widgets.get(item.id)
        if tile:
            tile.bind(item)
        if self._lightbox_index >= 0 and 0 <= self._lightbox_index < len(self._items):
            if self._items[self._lightbox_index].id == item.id:
                self.lightbox.show_item(item, self._lightbox_index, len(self._items))
        self.selection_changed.emit()

    def _render_single(self, item: ImageItem) -> None:
        if item.status == ItemStatus.QUEUED or item.status == ItemStatus.RUNNING:
            self.canvas.set_busy(True, "正在去除背景…\n（首次加载模型可能稍慢）")
        elif item.status == ItemStatus.FAILED:
            self.canvas.set_error(item.error or "处理失败")
        elif item.status == ItemStatus.DONE and item.result_image is not None:
            pix = pil_to_qpixmap(item.result_image)
            path = item.result_path or item.source_path
            original = None
            try:
                original = pil_to_qpixmap(load_preview_image(item.source_path))
            except Exception:
                original = None
            self.canvas.set_result(pix, path, original=original)
        else:
            self.canvas.set_idle()

    def _rebuild_grid(self) -> None:
        # clear
        while self.grid_layout.count():
            w = self.grid_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._tile_widgets.clear()

        cols = max(2, min(4, self.width() // 160))
        for idx, item in enumerate(self._items):
            tile = _GridTile(checker=self._checker)
            tile.bind(item)
            tile.clicked.connect(self._on_tile_click)
            tile.selection_toggled.connect(self._on_tile_select)
            tile.reprocess_requested.connect(self.reprocess_requested.emit)
            r, c = divmod(idx, cols)
            self.grid_layout.addWidget(tile, r, c)
            self._tile_widgets[item.id] = tile
        self.grid_layout.setRowStretch((len(self._items) + cols - 1) // cols, 1)
        self.selection_changed.emit()

    def selection_stats(self) -> tuple[int, int, int, bool]:
        """n, done, selected_count, all_selected."""
        n = len(self._items)
        done = sum(1 for i in self._items if i.status == ItemStatus.DONE)
        sel = sum(1 for i in self._items if i.selected)
        all_sel = bool(self._items) and all(i.selected for i in self._items)
        return n, done, sel, all_sel

    def item_for_copy(self) -> Optional[ImageItem]:
        """
        Resolve which result image Ctrl+C should copy:
        lightbox current → single session item → exactly one selected DONE.
        """
        def ok(item: Optional[ImageItem]) -> bool:
            return (
                item is not None
                and item.status == ItemStatus.DONE
                and item.result_image is not None
            )

        # Multi lightbox
        if (
            self.stack.currentWidget() is self.lightbox
            and 0 <= self._lightbox_index < len(self._items)
        ):
            item = self._items[self._lightbox_index]
            if ok(item):
                return item

        # Single preview
        if len(self._items) == 1 and ok(self._items[0]):
            return self._items[0]

        # Grid: exactly one selected completed item
        selected = [
            i
            for i in self._items
            if i.selected and i.status == ItemStatus.DONE and i.result_image is not None
        ]
        if len(selected) == 1:
            return selected[0]
        return None

    def set_select_all(self, checked: bool) -> None:
        for item in self._items:
            item.selected = checked
        for tile in self._tile_widgets.values():
            tile.sync_checkbox()
        self.selection_changed.emit()

    def invert_selection(self) -> None:
        if not self._items:
            return
        for item in self._items:
            item.selected = not item.selected
        for tile in self._tile_widgets.values():
            tile.sync_checkbox()
        self.selection_changed.emit()

    def _on_tile_select(self, item_id: str, selected: bool) -> None:
        for item in self._items:
            if item.id == item_id:
                item.selected = selected
                break
        self.selection_changed.emit()

    def _on_tile_click(self, item_id: str) -> None:
        for idx, item in enumerate(self._items):
            if item.id == item_id:
                self._show_lightbox(idx)
                return

    def _on_single_context_menu(self, pos) -> None:
        """Single-image canvas: right-click re-matte with a downloaded model."""
        if len(self._items) != 1:
            return
        item = self._items[0]
        can = item.status in (ItemStatus.DONE, ItemStatus.FAILED)
        menu = QMenu(self.canvas)

        def _pick(model_id: str) -> None:
            self.reprocess_requested.emit(item.id, model_id)

        _populate_reprocess_menu(menu, can_reprocess=can, on_pick_model=_pick)
        menu.exec(self.canvas.mapToGlobal(pos))

    def _show_lightbox(self, index: int) -> None:
        if not self._items:
            return
        self._lightbox_index = max(0, min(index, len(self._items) - 1))
        item = self._items[self._lightbox_index]
        # Switch page first so layout can compute real preview size, then paint.
        self.stack.setCurrentWidget(self.lightbox)
        self.lightbox.show_item(item, self._lightbox_index, len(self._items))
        # The current lightbox image is now the target for repair and copy.
        self.selection_changed.emit()

    def _close_lightbox(self) -> None:
        self._lightbox_index = -1
        if len(self._items) >= 2:
            self.stack.setCurrentWidget(self.grid_page)
            self._rebuild_grid()
        elif len(self._items) == 1:
            self.stack.setCurrentWidget(self.canvas)
            self._render_single(self._items[0])
        else:
            self.stack.setCurrentWidget(self.canvas)
            self.canvas.set_idle()

    def _on_lightbox_nav(self, delta: int) -> None:
        if not self._items:
            return
        self._lightbox_index = (self._lightbox_index + delta) % len(self._items)
        item = self._items[self._lightbox_index]
        self.lightbox.show_item(item, self._lightbox_index, len(self._items))
        self.selection_changed.emit()

    # drop on workspace (grid page also needs drops)
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if should_ignore_drop(event.mimeData()):
            event.ignore()
            return
        if paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        if should_ignore_drop(event.mimeData()):
            event.ignore()
            return
        paths = paths_from_mime(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self.paths_dropped.emit([str(p) for p in paths])
        else:
            event.ignore()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if len(self._items) >= 2 and self.stack.currentWidget() is self.grid_page:
            # debounce-ish: rebuild columns
            self._rebuild_grid()


class _GridTile(QFrame):
    clicked = Signal(str)
    selection_toggled = Signal(str, bool)
    reprocess_requested = Signal(str, str)  # item_id, model_id

    def __init__(
        self, checker: tuple[str, str] = ("#e6e6e8", "#ffffff"), parent=None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("GridTile")
        self.setFixedSize(140, 168)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self._item_id = ""
        self._item: Optional[ImageItem] = None
        self._checker = checker

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        top = QHBoxLayout()
        self.chk = QCheckBox()
        self.chk.setObjectName("TileCheck")
        self.chk.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.chk.setAutoFillBackground(False)
        self.chk.toggled.connect(self._on_chk)
        self.badge = QLabel("")
        self.badge.setObjectName("TileBadge")
        top.addWidget(self.chk)
        top.addStretch(1)
        top.addWidget(self.badge)
        lay.addLayout(top)

        self.thumb = QLabel()
        self.thumb.setFixedSize(120, 120)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setObjectName("TileThumb")
        lay.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignCenter)

        self.caption = QLabel("")
        self.caption.setObjectName("TileCaption")
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setWordWrap(True)
        lay.addWidget(self.caption)

    def set_checker(self, a: str, b: str) -> None:
        self._checker = (a, b)
        if self._item:
            self.bind(self._item)

    def bind(self, item: ImageItem) -> None:
        self._item = item
        self._item_id = item.id
        self.chk.blockSignals(True)
        self.chk.setChecked(item.selected)
        self.chk.blockSignals(False)
        name = item.name
        if len(name) > 18:
            name = name[:15] + "…"
        self.caption.setText(name)

        if item.status == ItemStatus.QUEUED:
            self.badge.setText("等待")
            self.thumb.setText("…")
            self.thumb.setPixmap(QPixmap())
        elif item.status == ItemStatus.RUNNING:
            self.badge.setText("处理中")
            self.thumb.setText("…")
            self.thumb.setPixmap(QPixmap())
        elif item.status == ItemStatus.FAILED:
            self.badge.setText("失败")
            self.thumb.setText("!")
            self.thumb.setPixmap(QPixmap())
        elif item.status == ItemStatus.DONE and item.result_image is not None:
            self.badge.setText("完成")
            pix = pil_to_qpixmap(item.result_image)
            scaled = pix.scaled(
                120,
                120,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            board = make_checkerboard(
                scaled.size(), color_a=self._checker[0], color_b=self._checker[1]
            )
            p = QPainter(board)
            p.drawPixmap(0, 0, scaled)
            p.end()
            self.thumb.setPixmap(board)
            self.thumb.setText("")
        else:
            self.badge.setText("")
            self.thumb.clear()

    def sync_checkbox(self) -> None:
        if self._item:
            self.chk.blockSignals(True)
            self.chk.setChecked(self._item.selected)
            self.chk.blockSignals(False)

    def _on_chk(self, checked: bool) -> None:
        self.selection_toggled.emit(self._item_id, checked)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            # ignore clicks on checkbox area roughly
            if self.chk.geometry().contains(event.position().toPoint()):
                super().mouseReleaseEvent(event)
                return
            self.clicked.emit(self._item_id)
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        """Right-click: re-matte this tile with a downloaded model."""
        item = self._item
        can = item is not None and item.status in (
            ItemStatus.DONE,
            ItemStatus.FAILED,
        )
        menu = QMenu(self)

        def _pick(model_id: str) -> None:
            self.reprocess_requested.emit(self._item_id, model_id)

        _populate_reprocess_menu(menu, can_reprocess=can, on_pick_model=_pick)
        menu.exec(event.globalPos())
        event.accept()


class Lightbox(QWidget):
    """Multi-item single-frame preview: same F09 compare as DropCanvas."""

    closed = Signal()
    changed = Signal(int)  # delta -1 / +1

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Lightbox")
        self._checker = ("#e6e6e8", "#ffffff")
        self._item: Optional[ImageItem] = None
        self._press: Optional[QPoint] = None
        self._index = 0
        self._total = 0
        self._paint_pending = False

        self._result_pixmap: Optional[QPixmap] = None
        self._original_pixmap: Optional[QPixmap] = None
        self._original_key: Optional[str] = None
        self._side_by_side = False
        self._hold_side: Optional[str] = None  # None | full | left | right
        self._press_active = False
        self._drag_started = False
        self._long_press_ms = 180
        self._drag_threshold = 10
        self._long_press_timer = QTimer(self)
        self._long_press_timer.setSingleShot(True)
        self._long_press_timer.timeout.connect(self._on_long_press)

        lay = QVBoxLayout(self)
        # Tight chrome → larger image
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)

        top = QHBoxLayout()
        top.setContentsMargins(4, 0, 4, 0)
        self.lbl_title = QLabel("")
        self.lbl_title.setObjectName("HeroHint")
        self.lbl_title.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        top.addWidget(self.lbl_title)
        top.addStretch(1)
        lay.addLayout(top, 0)

        mid = QHBoxLayout()
        mid.setSpacing(4)
        self.btn_prev = QPushButton("←")
        self.btn_prev.setObjectName("LightboxNavBtn")
        self.btn_prev.setFixedSize(40, 40)
        self.btn_prev.clicked.connect(lambda: self.changed.emit(-1))
        self.btn_next = QPushButton("→")
        self.btn_next.setObjectName("LightboxNavBtn")
        self.btn_next.setFixedSize(40, 40)
        self.btn_next.clicked.connect(lambda: self.changed.emit(1))
        # FitPixmapLabel: sizeHint ignores pixmap so chrome stays below the image
        self.preview = FitPixmapLabel()
        self.preview.setObjectName("PreviewLabel")
        self.preview.setToolTip(
            "右键回网格 · 长按/空格看原图 · 拖移拖出结果 · ← → 换图"
        )
        self.preview.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        mid.addWidget(self.btn_prev, 0, Qt.AlignmentFlag.AlignVCenter)
        mid.addWidget(self.preview, 1)
        mid.addWidget(self.btn_next, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(mid, 1)

        # Compact single-row chrome under image (compare + short tip)
        chrome = QWidget()
        chrome.setObjectName("LightboxChrome")
        chrome.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        chrome_l = QHBoxLayout(chrome)
        chrome_l.setContentsMargins(0, 2, 0, 0)
        chrome_l.setSpacing(10)

        self.btn_side_by_side = QPushButton("左右对照")
        self.btn_side_by_side.setObjectName("CompareBtn")
        self.btn_side_by_side.setCheckable(True)
        self.btn_side_by_side.setToolTip(
            "左原图 · 右结果。长按某一侧在原位临时换成另一张，松开恢复。"
        )
        self.btn_side_by_side.toggled.connect(self._on_side_by_side_toggled)
        chrome_l.addStretch(1)
        chrome_l.addWidget(self.btn_side_by_side, 0)
        self.hint = QLabel("长按对照 · 右键回网格 · 拖出")
        self.hint.setObjectName("DragOutHint")
        self.hint.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.hint.setWordWrap(False)
        self.hint.setToolTip(
            "← → 换图 · 长按/空格看原图 · 并排时侧边长按互换 · 右键回网格 · 拖出结果"
        )
        self.hint.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self.hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        chrome_l.addWidget(self.hint, 0)
        chrome_l.addStretch(1)
        lay.addWidget(chrome, 0)

    def apply_theme_colors(self, *, checker_a: str, checker_b: str) -> None:
        self._checker = (checker_a, checker_b)
        if self._item:
            self._schedule_paint()

    def show_item(self, item: ImageItem, index: int, total: int) -> None:
        self._item = item
        self._index = index
        self._total = total
        self._hold_side = None
        self._press_active = False
        self._drag_started = False
        self._long_press_timer.stop()
        self._press = None
        self.lbl_title.setText(f"{index + 1} / {total}  ·  {item.name}")
        self._load_pixmaps(item)
        can = self._has_original() and item.status == ItemStatus.DONE
        self.btn_side_by_side.setEnabled(can)
        self.btn_side_by_side.setVisible(
            item.status == ItemStatus.DONE and item.result_image is not None
        )
        # keep side_by_side across items if still possible
        if not can:
            self._side_by_side = False
        self.btn_side_by_side.blockSignals(True)
        self.btn_side_by_side.setChecked(self._side_by_side and can)
        self.btn_side_by_side.blockSignals(False)
        self._schedule_paint()

    def set_hold_peek(self, on: bool) -> None:
        if not self._item or self._item.status != ItemStatus.DONE:
            return
        if not self._has_original():
            return
        if on:
            side = "right" if self._side_by_side else "full"
            if self._hold_side == side:
                return
            self._hold_side = side
        else:
            if self._hold_side is None:
                return
            self._hold_side = None
        self._paint_item(self._item)

    def _has_original(self) -> bool:
        return (
            self._original_pixmap is not None and not self._original_pixmap.isNull()
        )

    def _load_pixmaps(self, item: ImageItem) -> None:
        if item.status == ItemStatus.DONE and item.result_image is not None:
            self._result_pixmap = pil_to_qpixmap(item.result_image)
        else:
            self._result_pixmap = None

        try:
            key = str(item.source_path.resolve())
        except Exception:
            key = str(item.source_path) if item.source_path else ""
        if key and key == self._original_key and self._has_original():
            return
        self._original_key = key or None
        self._original_pixmap = None
        if item.source_path and item.source_path.is_file():
            try:
                self._original_pixmap = pil_to_qpixmap(
                    load_preview_image(item.source_path)
                )
            except Exception:
                self._original_pixmap = None

    def _on_side_by_side_toggled(self, checked: bool) -> None:
        if checked and not self._has_original():
            self.btn_side_by_side.blockSignals(True)
            self.btn_side_by_side.setChecked(False)
            self.btn_side_by_side.blockSignals(False)
            return
        self._side_by_side = bool(checked)
        self._hold_side = None
        if self._item is not None:
            self._paint_item(self._item)

    def _hit_compare_side(self, widget_pos: QPoint) -> str:
        if not self._side_by_side:
            return "full"
        pl = self.preview.mapFrom(self, widget_pos)
        pm = self.preview.pixmap()
        if pm is None or pm.isNull():
            return "right"
        avail = self.preview.size()
        ox = max(0, (avail.width() - pm.width()) // 2)
        x = pl.x() - ox
        if x < 0 or x >= pm.width():
            return "left" if pl.x() < avail.width() / 2 else "right"
        return "left" if x < pm.width() / 2 else "right"

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._schedule_paint()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._item is not None:
            self._schedule_paint()

    def _schedule_paint(self) -> None:
        if self._paint_pending:
            return
        self._paint_pending = True
        QTimer.singleShot(0, self._do_scheduled_paint)

    def _do_scheduled_paint(self) -> None:
        self._paint_pending = False
        if self._item is not None:
            self._paint_item(self._item)

    def _preview_avail_size(self) -> QSize:
        """Scale target = actual preview widget size only (never full lightbox)."""
        avail = self.preview.size()
        if avail.width() >= 40 and avail.height() >= 40:
            return avail
        # Before first layout pass
        return QSize(200, 200)

    def _paint_item(self, item: ImageItem) -> None:
        if item.status == ItemStatus.FAILED:
            self.preview.setPixmap(QPixmap())
            self.preview.setText(item.error or "失败")
            self.preview.setCursor(Qt.CursorShape.ArrowCursor)
            return
        if item.status != ItemStatus.DONE or self._result_pixmap is None:
            self.preview.setPixmap(QPixmap())
            self.preview.setText(
                "处理中…" if item.status == ItemStatus.RUNNING else "等待中…"
            )
            self.preview.setCursor(Qt.CursorShape.ArrowCursor)
            return

        avail = self._preview_avail_size()
        if self._hold_side == "full" and self._has_original():
            assert self._original_pixmap is not None
            self.preview.setPixmap(
                paint_hold_original(self._original_pixmap, avail)
            )
            self.preview.setText("")
            self.preview.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if self._side_by_side and self._has_original():
            assert self._original_pixmap is not None
            self.preview.setPixmap(
                compose_side_by_side(
                    self._original_pixmap,
                    self._result_pixmap,
                    avail,
                    self._checker[0],
                    self._checker[1],
                    flip_left=self._hold_side == "left",
                    flip_right=self._hold_side == "right",
                )
            )
            self.preview.setText("")
            cursor = (
                Qt.CursorShape.ArrowCursor
                if self._hold_side in ("left", "right")
                else Qt.CursorShape.OpenHandCursor
            )
            self.preview.setCursor(cursor)
            return

        self.preview.setPixmap(
            scale_with_checker(
                self._result_pixmap,
                avail,
                self._checker[0],
                self._checker[1],
            )
        )
        self.preview.setText("")
        self.preview.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            self._long_press_timer.stop()
            self._hold_side = None
            self._press = None
            self._press_active = False
            self.closed.emit()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.position().toPoint()
            self._press_active = True
            self._drag_started = False
            if (
                self._item
                and self._item.status == ItemStatus.DONE
                and self._has_original()
            ):
                self._long_press_timer.start(self._long_press_ms)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (
            self._press_active
            and self._press is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and not self._drag_started
        ):
            dist = (event.position().toPoint() - self._press).manhattanLength()
            if dist >= self._drag_threshold:
                self._long_press_timer.stop()
                if self._hold_side is not None and self._item is not None:
                    self._hold_side = None
                    self._paint_item(self._item)
                if (
                    self._item
                    and self._item.status == ItemStatus.DONE
                    and self._item.result_path
                    and self._item.result_path.is_file()
                ):
                    self._drag_started = True
                    self._press_active = False
                    self._drag_out()
                    self._press = None
                    return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._long_press_timer.stop()
            if self._hold_side is not None and self._item is not None:
                self._hold_side = None
                self._paint_item(self._item)
            self._press_active = False
            self._drag_started = False
            self._press = None
        super().mouseReleaseEvent(event)

    def _on_long_press(self) -> None:
        if not self._press_active or self._drag_started:
            return
        if not self._item or self._item.status != ItemStatus.DONE:
            return
        if not self._has_original():
            return
        pos = self._press or QPoint(0, 0)
        self._hold_side = self._hit_compare_side(pos)
        self._paint_item(self._item)

    def _drag_out(self) -> None:
        if not self._item or not self._item.result_path:
            return
        if not self._item.result_path.is_file():
            return
        drag = QDrag(self)
        mime = QMimeData()
        url = QUrl.fromLocalFile(str(self._item.result_path.resolve()))
        mime.setUrls([url])
        mime.setText(str(self._item.result_path.resolve()))
        mime.setData(PEEL_INTERNAL_MIME, b"1")
        drag.setMimeData(mime)
        begin_internal_drag_out()
        try:
            drag.exec(Qt.DropAction.CopyAction)
        finally:
            end_internal_drag_out()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.closed.emit()
        elif event.key() == Qt.Key.Key_Left:
            self.changed.emit(-1)
        elif event.key() == Qt.Key.Key_Right:
            self.changed.emit(1)
        else:
            super().keyPressEvent(event)
