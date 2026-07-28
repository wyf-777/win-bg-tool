from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, Signal, Slot, QObject, QEvent
from PySide6.QtGui import QKeySequence, QShortcut, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QStatusBar,
)

from app.engines.local_rembg import LocalRembgEngine
from app.engines.models_catalog import get_model_info
from app.services.export import (
    export_image,
    file_filter_for_format,
    resolve_export_format,
)
from app.services.hotkeys import get_hotkey, sequence_matches_event
from app.services.settings import (
    get_alpha_matting,
    get_export_custom_ext,
    get_export_format,
    get_export_prefix,
    get_model,
    get_theme,
)
from app.session.batch_session import BatchSession
from app.session.limits import MAX_DROP, MAX_SESSION
from app.session.models import ItemStatus
from app.ui.errors import friendly_error
from app.ui.settings_dialog import SettingsPage
from app.ui.theme import build_stylesheet, resolve_theme
from app.ui.widgets import (
    SlideClearButton,
    SlideExportButton,
    SlideOpenButton,
    SlideSettingsButton,
)
from app.ui.workspace import Workspace


class MainWindow(QMainWindow):
    # Cross-thread download progress (worker → UI)
    engine_progress = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Peel — 去背景")
        self.resize(720, 720)
        # Min size leaves room for top chrome + footer actions + status
        self.setMinimumSize(480, 480)

        self._theme_pref = get_theme()
        self._export_prefix = get_export_prefix()
        self.engine = LocalRembgEngine(
            model_name=get_model(),
            alpha_matting=get_alpha_matting(),
        )
        self.engine_progress.connect(self._show_engine_progress)
        # Download progress → status bar (may fire from worker threads)
        self.engine.set_progress_callback(
            lambda m: self.engine_progress.emit(m)
        )
        self.session = BatchSession(
            self.engine, self, export_prefix=self._export_prefix
        )

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Full-window stack: main app | Edge-style settings
        self.root_stack = QStackedWidget()
        outer.addWidget(self.root_stack, 1)

        # ── Page 0: main ───────────────────────────────────
        main_page = QWidget()
        root = QVBoxLayout(main_page)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        top = QHBoxLayout()
        brand = QLabel("🥝  Peel")
        brand.setObjectName("BrandLabel")
        self.model_label = QLabel("本机 · 就绪")
        self.model_label.setObjectName("ModelLabel")
        self.model_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.btn_settings = SlideSettingsButton()
        self.btn_settings.clicked.connect(self.open_settings)
        top.addWidget(brand)
        top.addStretch(1)
        top.addWidget(self.model_label)
        top.addSpacing(8)
        top.addWidget(self.btn_settings)
        root.addLayout(top)

        self.workspace = Workspace()
        self.workspace.paths_dropped.connect(self.add_paths)
        self.workspace.open_clicked.connect(self.open_files)
        self.workspace.request_export_selected.connect(self.export_selected)
        self.workspace.request_export_all.connect(self.export_all)
        self.workspace.selection_changed.connect(self._refresh_chrome)
        root.addWidget(self.workspace, 1)

        # Footer chrome: pin height so shrinking never pushes buttons into canvas
        # (Yiyin-style: batch strip + actions + foot hint)
        footer = QWidget()
        footer.setObjectName("MainFooter")
        footer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        bottom = QVBoxLayout(footer)
        bottom.setContentsMargins(0, 8, 0, 0)
        bottom.setSpacing(8)

        self.batch_bar = QWidget()
        self.batch_bar.setObjectName("BatchBar")
        self.batch_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        batch_l = QHBoxLayout(self.batch_bar)
        batch_l.setContentsMargins(14, 8, 14, 8)
        batch_l.setSpacing(16)
        self.chk_select_all = QCheckBox("全选")
        self.chk_select_all.setObjectName("BatchCheck")
        self.chk_select_all.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        self.chk_select_all.setAutoFillBackground(False)
        self.chk_select_all.setToolTip("全选 / 取消全选网格中的图片")
        self.chk_select_all.toggled.connect(self._on_select_all_toggled)
        self.chk_invert = QCheckBox("反选")
        self.chk_invert.setObjectName("BatchCheck")
        self.chk_invert.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        self.chk_invert.setAutoFillBackground(False)
        self.chk_invert.setToolTip("勾选后立即反转选中，并自动复位")
        self.chk_invert.toggled.connect(self._on_invert_toggled)
        self.lbl_batch_info = QLabel("")
        self.lbl_batch_info.setObjectName("BatchInfoLabel")
        self.lbl_batch_info.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        batch_l.addWidget(self.chk_select_all)
        batch_l.addWidget(self.chk_invert)
        batch_l.addStretch(1)
        batch_l.addWidget(self.lbl_batch_info)
        self.batch_bar.hide()
        bottom.addWidget(self.batch_bar)

        actions_host = QWidget()
        actions_host.setObjectName("MainActionsBar")
        actions_host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        actions_host.setMinimumHeight(40)
        actions = QHBoxLayout(actions_host)
        actions.setSpacing(8)
        actions.setContentsMargins(0, 0, 0, 0)

        self.btn_open = SlideOpenButton()
        self.btn_open.clicked.connect(self.open_files)

        # Secondary actions — same height as capsules (36 visual)
        self.btn_clear = SlideClearButton()
        self.btn_clear.setEnabled(False)
        self.btn_clear.clicked.connect(self.clear_session)

        self.btn_export_sel = QPushButton("导出选中")
        self.btn_export_sel.setObjectName("ActionBtn")
        self.btn_export_sel.setFixedHeight(36)
        self.btn_export_sel.setMinimumWidth(72)
        self.btn_export_sel.setEnabled(False)
        self.btn_export_sel.clicked.connect(self.export_selected)

        self.btn_save = SlideExportButton()
        self.btn_save.set_text("导出")
        # Keep always interactive (like 设置/打开) so hover anim works;
        # export_smart() still no-ops with a message when nothing is ready.
        self.btn_save.setEnabled(True)
        self.btn_save.clicked.connect(self.export_smart)

        actions.addWidget(
            self.btn_open, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        actions.addStretch(1)
        actions.addWidget(self.btn_clear, 0, Qt.AlignmentFlag.AlignVCenter)
        actions.addWidget(self.btn_export_sel, 0, Qt.AlignmentFlag.AlignVCenter)
        actions.addWidget(self.btn_save, 0, Qt.AlignmentFlag.AlignVCenter)
        bottom.addWidget(actions_host)

        self.foot = QLabel("拖入图片 · 本机处理 · 不上传")
        self.foot.setObjectName("FootHint")
        self.foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.foot.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        bottom.addWidget(self.foot)

        root.addWidget(footer, 0)

        self.root_stack.addWidget(main_page)

        # ── Page 1: settings (full window) ─────────────────
        self.settings_page = SettingsPage()
        self.settings_page.back_requested.connect(self.close_settings)
        self.settings_page.theme_changed.connect(self._on_theme_changed)
        self.settings_page.model_changed.connect(self._on_model_setting_changed)
        self.settings_page.export_prefix_changed.connect(self._on_prefix_changed)
        self.settings_page.export_format_changed.connect(self._on_format_changed)
        self.settings_page.alpha_matting_changed.connect(self._on_alpha_changed)
        self.settings_page.hotkeys_changed.connect(self.reload_hotkeys)
        self.root_stack.addWidget(self.settings_page)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("准备就绪")

        self.session.items_changed.connect(self._on_items_changed)
        self.session.item_updated.connect(self._on_item_updated)
        self.session.busy_changed.connect(self._on_busy_changed)
        self.session.status_message.connect(self.statusBar().showMessage)
        self.session.model_name_changed.connect(self._on_model_name)

        self._apply_theme()

        app = QApplication.instance()
        if app is not None:
            app.styleHints().colorSchemeChanged.connect(self._on_system_scheme_changed)

        # User-rebindable hotkeys (Valorant-style); fixed nav keys separate
        self._hotkey_shortcuts: dict[str, QShortcut] = {}
        self._hotkey_slots = {
            "open": self.open_files,
            "export": self.export_smart,
            "copy": self.copy_result,
            "paste": self.paste_from_clipboard,
            "settings": self.open_settings,
        }
        self.reload_hotkeys()

        self._sc_esc = QShortcut(QKeySequence("Esc"), self, self._on_escape)
        self._sc_left = QShortcut(
            QKeySequence(Qt.Key.Key_Left), self, lambda: self._lightbox_nav(-1)
        )
        self._sc_right = QShortcut(
            QKeySequence(Qt.Key.Key_Right), self, lambda: self._lightbox_nav(1)
        )
        # Esc must not steal key from QComboBox popup / line edit
        self._sc_esc.setContext(Qt.ShortcutContext.WindowShortcut)
        # Space hold = peek original (handled in keyPress/Release, not QShortcut)

        # App-wide filter so "copy" works even when a child widget has focus
        self._copy_filter = _CopyHotkeyFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self._copy_filter)

        self._start_model_warmup()
        self._refresh_chrome()
        # show configured model id until warmup finishes
        self.model_label.setText(f"本机 · {get_model()}")

    def reload_hotkeys(self) -> None:
        """Load rebindable shortcuts from settings (open/export/copy/paste/settings)."""
        for aid, slot in self._hotkey_slots.items():
            seq = get_hotkey(aid)
            sc = self._hotkey_shortcuts.get(aid)
            if sc is None:
                sc = QShortcut(self)
                sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
                sc.activated.connect(slot)
                self._hotkey_shortcuts[aid] = sc
            sc.setKey(QKeySequence(seq) if seq else QKeySequence())
            sc.setEnabled(bool(seq))

    # ── Theme ──────────────────────────────────────────────

    def _apply_theme(self) -> None:
        colors = resolve_theme(self._theme_pref)
        sheet = build_stylesheet(colors)
        # Capsule buttons paint their own pill; sync theme colors
        capsule_kwargs = dict(
            bg=colors.button_bg,
            border=colors.button_border,
            hover=colors.button_hover,
            pressed=colors.button_pressed,
            disabled_bg=colors.button_disabled_bg,
            primary=colors.primary,
            text=colors.text,
            disabled_text=colors.button_disabled_text,
        )
        for attr in ("btn_settings", "btn_open", "btn_clear", "btn_save"):
            btn = getattr(self, attr, None)
            if btn is not None and hasattr(btn, "apply_theme_colors"):
                btn.apply_theme_colors(**capsule_kwargs)
        # Settings page back button (created with settings_page)
        if hasattr(self, "settings_page") and hasattr(self.settings_page, "btn_back"):
            back = self.settings_page.btn_back
            if hasattr(back, "apply_theme_colors"):
                back.apply_theme_colors(**capsule_kwargs)
        # extra styles for grid tiles
        sheet += f"""
        #GridTile {{
            background: {colors.card_bg};
            border: 1px solid {colors.card_border};
            border-radius: 12px;
        }}
        #TileCaption, #TileBadge, #TileThumb {{
            color: {colors.muted};
            font-size: 11px;
            background: transparent;
            border: none;
        }}
        #TileCheck {{
            background: transparent;
            border: none;
        }}
        #Lightbox {{
            background: {colors.window_bg};
        }}
        #GridScroll {{
            background: transparent;
            border: none;
        }}
        """
        self.setStyleSheet(sheet)
        self.workspace.apply_theme_colors(
            checker_a=colors.checker_a,
            checker_b=colors.checker_b,
            accent_dash=colors.accent_dash,
        )

    @Slot(str)
    def _on_theme_changed(self, theme: str) -> None:
        self._theme_pref = theme
        self._apply_theme()
        label = {"light": "浅色", "dark": "深色", "system": "跟随系统"}.get(theme, theme)
        self.statusBar().showMessage(f"主题：{label}（仅本程序）")

    @Slot()
    def _on_system_scheme_changed(self) -> None:
        if self._theme_pref == "system":
            self._apply_theme()

    def is_settings_open(self) -> bool:
        return self.root_stack.currentWidget() is self.settings_page

    def _set_main_shortcuts_enabled(self, enabled: bool) -> None:
        """Disable main-app shortcuts while settings is open (avoid accidental exit)."""
        for sc in self._hotkey_shortcuts.values():
            if enabled:
                sc.setEnabled(not sc.key().isEmpty())
            else:
                sc.setEnabled(False)
        for sc in (self._sc_left, self._sc_right):
            sc.setEnabled(enabled)
        # Esc stays enabled but handled carefully in _on_escape
        if not enabled:
            self.workspace.set_hold_peek(False)

    @Slot()
    def open_settings(self) -> None:
        # Always allow settings — e.g. switch to a local model while another
        # model is still downloading (download will be cancelled).
        self._set_main_shortcuts_enabled(False)
        self.root_stack.setCurrentWidget(self.settings_page)
        if self.session.is_busy() or self.engine.is_loading():
            self.statusBar().showMessage(
                "设置 — 处理/下载中也可切换到「本地已有」的模型；"
                "换模型会取消当前下载"
            )
        else:
            self.statusBar().showMessage(
                "设置 — 左侧点分类 · 改完点左上角「返回」（Esc 不会退出设置）"
            )

    @Slot()
    def close_settings(self) -> None:
        self.root_stack.setCurrentIndex(0)
        self._set_main_shortcuts_enabled(True)
        self.statusBar().showMessage("已返回主界面")

    @Slot(str)
    def _on_model_setting_changed(self, model_id: str) -> None:
        # Allowed while busy/downloading: set_model bumps gen → cancels download
        was_loading = self.engine.is_loading() or not self.engine.is_model_file_present(
            self.engine.model_name
        )
        self.engine.set_model(model_id)
        info = get_model_info(model_id)
        label = info.label if info else model_id
        self.model_label.setText(f"本机 · {model_id}")
        if self.engine.is_model_file_present(model_id):
            tip = f"已切换模型：{label}（本地已有"
            if was_loading:
                tip += "，已取消先前下载"
            tip += "，后台加载中）"
            self.statusBar().showMessage(tip)
        else:
            self.statusBar().showMessage(
                f"已切换模型：{label} — 首次使用，正在后台下载…"
                f"可随时再换回本地模型以取消下载"
            )
        # Warm new model (or continue queue with new model)
        self._start_model_warmup()

    @Slot(str)
    def _on_prefix_changed(self, prefix: str) -> None:
        self._export_prefix = prefix
        self.session.set_export_prefix(prefix)
        self.statusBar().showMessage(f"导出前缀：{prefix}")

    @Slot(str)
    def _on_format_changed(self, fmt_id: str) -> None:
        _pf, suffix, alpha = resolve_export_format(fmt_id, get_export_custom_ext())
        tip = "保留透明" if alpha else "不透明（白底）"
        self.statusBar().showMessage(f"默认导出格式：{suffix}（{tip}）")
        self._refresh_chrome()

    @Slot(bool)
    def _on_alpha_changed(self, enabled: bool) -> None:
        self.engine.set_alpha_matting(enabled)
        self.statusBar().showMessage(
            "Alpha Matting 已开启（更慢、边缘更细）"
            if enabled
            else "Alpha Matting 已关闭"
        )

    @Slot(str)
    def _show_engine_progress(self, msg: str) -> None:
        if msg:
            self.statusBar().showMessage(msg)

    def _start_model_warmup(self) -> None:
        # Defer slightly so first UI paint / hover isn't fighting ONNX load.
        # Model switch still eventually warms; gen counter discards stale threads.
        from PySide6.QtCore import QTimer

        QTimer.singleShot(400, self._run_model_warmup)

    def _run_model_warmup(self) -> None:
        # Avoid stacking warmups: one thread + engine lock = single download.
        # If a previous warmup is still running, set_model already bumped gen;
        # that thread will re-ensure the new model after it finishes.
        t = getattr(self, "_warmup_thread", None)
        if t is not None and t.isRunning():
            if not self.engine.is_model_file_present():
                self.statusBar().showMessage(
                    f"模型「{self.engine.model_name}」下载/加载中…"
                    f"请勿退出，完成后可用"
                )
            return
        if not self.engine.is_model_file_present():
            self.statusBar().showMessage(
                f"正在下载模型「{get_model()}」…请保持联网，勿中途退出"
            )
        self._warmup_thread = _WarmupThread(self.engine)
        self._warmup_thread.done.connect(self._on_warmup)
        self._warmup_thread.failed.connect(self._on_warmup_failed)
        self._warmup_thread.start()

    # ── Session chrome ─────────────────────────────────────

    def _refresh_chrome(self) -> None:
        n = self.session.count()
        busy = self.session.is_busy()
        multi = n >= 2
        self.btn_open.setEnabled(not busy)
        # Settings always clickable — switch to a local model while downloading
        self.btn_settings.setEnabled(True)
        self.btn_clear.setEnabled(n > 0 and not busy)
        # Export as soon as any item is DONE (don't wait for whole batch / download)
        has_done = any(
            i.status == ItemStatus.DONE and i.result_image is not None
            for i in self.session.items
        )
        has_sel_done = any(
            i.selected
            and i.status == ItemStatus.DONE
            and i.result_image is not None
            for i in self.session.items
        )
        _pf, suffix, _a = resolve_export_format(
            get_export_format(), get_export_custom_ext()
        )

        # Secondary strip: selection only when multi
        self.batch_bar.setVisible(multi)
        # 导出选中: multi only; 清除 always when has items
        self.btn_export_sel.setVisible(multi)
        self.chk_invert.setEnabled(multi and not busy and n > 0)
        # Allow export of finished items even while others are still processing
        self.btn_export_sel.setEnabled(multi and has_sel_done)

        if multi:
            _n, done, sel, all_sel = self.workspace.selection_stats()
            self.lbl_batch_info.setText(f"{_n} 张  ·  完成 {done}  ·  已选 {sel}")
            self.chk_select_all.blockSignals(True)
            self.chk_select_all.setChecked(all_sel)
            self.chk_select_all.setEnabled(not busy and n > 0)
            self.chk_select_all.blockSignals(False)
            self.chk_invert.blockSignals(True)
            self.chk_invert.setChecked(False)
            self.chk_invert.blockSignals(False)
            if hasattr(self.btn_clear, "set_text"):
                self.btn_clear.set_text("清除")
            self.btn_save.set_text("导出全部")
            # Do not setEnabled(False) — gray disable killed hover like 打开/设置 never do
            self.btn_save.setEnabled(True)
        else:
            self.lbl_batch_info.setText("")
            self.chk_select_all.blockSignals(True)
            self.chk_select_all.setChecked(False)
            self.chk_select_all.setEnabled(False)
            self.chk_select_all.blockSignals(False)
            self.chk_invert.blockSignals(True)
            self.chk_invert.setChecked(False)
            self.chk_invert.setEnabled(False)
            self.chk_invert.blockSignals(False)
            if hasattr(self.btn_clear, "set_text"):
                self.btn_clear.set_text("清除")
            self.btn_save.set_text(f"导出 {suffix.lstrip('.').upper()}")
            self.btn_save.setEnabled(True)

    @Slot(bool)
    def _on_select_all_toggled(self, checked: bool) -> None:
        self.workspace.set_select_all(checked)

    @Slot(bool)
    def _on_invert_toggled(self, checked: bool) -> None:
        """Checkbox UI like 全选; checking it inverts selection then resets."""
        if not checked:
            return
        self.workspace.invert_selection()
        self.chk_invert.blockSignals(True)
        self.chk_invert.setChecked(False)
        self.chk_invert.blockSignals(False)

    @Slot()
    def _on_items_changed(self) -> None:
        self.workspace.set_items(self.session.items)
        self._refresh_chrome()

    @Slot(str)
    def _on_item_updated(self, item_id: str) -> None:
        item = self.session.get(item_id)
        if item:
            # ensure workspace list ref is same objects
            self.workspace._items = self.session.items  # noqa: SLF001
            self.workspace.update_item(item)
        self._refresh_chrome()

    @Slot(bool)
    def _on_busy_changed(self, busy: bool) -> None:
        self._refresh_chrome()
        if not busy and self.session.count() > 0:
            self.workspace.set_items(self.session.items)

    @Slot(str)
    def _on_model_name(self, name: str) -> None:
        self.model_label.setText(f"本机 · {name}")

    # ── Add images ─────────────────────────────────────────

    @Slot()
    def open_files(self) -> None:
        if self.session.is_busy():
            QMessageBox.information(
                self,
                "请稍候",
                "当前批次仍在处理，请等待全部完成后再添加图片。",
            )
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图片（可多选）",
            "",
            "图片 (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.gif);;所有文件 (*.*)",
        )
        if paths:
            self.add_paths(paths)

    @Slot(list)
    def add_paths(self, paths: list) -> None:
        if self.session.is_busy():
            QMessageBox.information(
                self,
                "请稍候",
                "当前批次仍在处理，请等待全部完成后再添加图片。",
            )
            return
        added, msg = self.session.add_paths(paths)
        if added == 0 and msg:
            # only show modal if nothing added and looks like a hard reject
            if "仍在处理" in msg or "上限" in msg:
                QMessageBox.information(self, "无法添加", msg)

    @Slot()
    def paste_from_clipboard(self) -> None:
        if self.session.is_busy():
            self.statusBar().showMessage("正在处理，请稍候…")
            return
        clip = QApplication.clipboard()
        if clip is None:
            return
        md = clip.mimeData()
        paths: List[str] = []
        if md is not None and md.hasUrls():
            for url in md.urls():
                if url.isLocalFile():
                    paths.append(url.toLocalFile())
        if paths:
            self.add_paths(paths)
            return
        qimg = clip.image()
        if qimg is not None and not qimg.isNull():
            import tempfile

            tmp = Path(tempfile.gettempdir()) / "win-bg-tool-clipboard.png"
            if qimg.save(str(tmp), "PNG"):
                self.add_paths([str(tmp)])
                return
        self.statusBar().showMessage("剪贴板中没有可用图片")

    @Slot()
    def copy_result(self) -> None:
        """Copy current result image to clipboard (default Ctrl+C, rebindable)."""
        # Debounce: shortcut + keyPress + event filter may all fire once
        from PySide6.QtCore import QTimer

        now = getattr(self, "_copy_last_ms", 0)
        from time import time as _time

        t = int(_time() * 1000)
        if t - now < 400:
            return
        self._copy_last_ms = t

        # Always surface feedback on the status bar (bottom of window)
        sb = self.statusBar()
        sb.setVisible(True)

        copy_disp = (
            QKeySequence(get_hotkey("copy")).toString(
                QKeySequence.SequenceFormat.NativeText
            )
            or "复制快捷键"
        )

        if self.is_settings_open():
            sb.showMessage(f"请先点「返回」到主界面，再 {copy_disp} 复制", 6000)
            return
        if self.session.is_busy():
            sb.showMessage("正在处理，请稍候再复制…", 6000)
            return

        # Prefer session items (source of truth) over workspace cache
        item = self._resolve_copy_item()

        if item is None or item.result_image is None:
            n = self.session.count()
            done_n = self.session.done_count()
            if n == 0:
                sb.showMessage("没有可复制的结果（请先打开并处理一张图）", 6000)
            elif done_n == 0:
                sb.showMessage("还没有处理完成的图片，无法复制", 6000)
            elif n >= 2:
                sb.showMessage(
                    f"多图请：双击进灯箱，或只勾选一张已完成的图，再 {copy_disp}",
                    8000,
                )
            else:
                sb.showMessage("当前图片尚未处理完成，无法复制", 6000)
            return

        from app.services.clipboard import copy_pil_image

        ok, msg = copy_pil_image(item.result_image)
        if ok:
            sb.showMessage(msg, 8000)
            # Title flash — easier to notice than status bar alone
            old = self.windowTitle()
            self.setWindowTitle("✓ 已复制到剪贴板")
            QTimer.singleShot(1500, lambda o=old: self.setWindowTitle(o))
        else:
            sb.showMessage(msg, 8000)
            QMessageBox.warning(self, "复制失败", msg)

    def _resolve_copy_item(self):
        """Pick which finished item the copy hotkey should copy."""
        items = self.session.items
        done = [
            i
            for i in items
            if i.status == ItemStatus.DONE and i.result_image is not None
        ]
        if not done:
            return None

        # 1) Lightbox current
        ws = self.workspace
        if (
            ws.stack.currentWidget() is ws.lightbox
            and 0 <= ws._lightbox_index < len(ws._items)  # noqa: SLF001
        ):
            cur = ws._items[ws._lightbox_index]  # noqa: SLF001
            if cur.status == ItemStatus.DONE and cur.result_image is not None:
                return cur
            # map by id into session
            for i in done:
                if i.id == cur.id:
                    return i

        # 2) Single image session
        if len(items) == 1 and done:
            return done[0]

        # 3) Exactly one selected done
        sel = [i for i in done if i.selected]
        if len(sel) == 1:
            return sel[0]

        # 4) Only one done in whole session
        if len(done) == 1:
            return done[0]

        return None

    # ── Export ─────────────────────────────────────────────

    @Slot()
    def export_smart(self) -> None:
        done = [
            i
            for i in self.session.items
            if i.status == ItemStatus.DONE and i.result_image is not None
        ]
        if not done:
            if self.session.is_busy():
                self.statusBar().showMessage("还在处理，完成后再导出…", 4000)
            elif self.session.count() == 0:
                self.statusBar().showMessage("请先打开或拖入图片", 4000)
            else:
                self.statusBar().showMessage("还没有处理完成的图片，无法导出", 4000)
            return
        if len(self.session.items) == 1:
            self._export_items(done, single_dialog=True)
        else:
            self.export_all()

    @Slot()
    def export_selected(self) -> None:
        items = [
            i
            for i in self.session.items
            if i.selected and i.status == ItemStatus.DONE and i.result_image is not None
        ]
        if not items:
            QMessageBox.information(self, "导出", "请先勾选已完成的图片。")
            return
        self._export_items(items, single_dialog=False)

    @Slot()
    def export_all(self) -> None:
        items = [
            i
            for i in self.session.items
            if i.status == ItemStatus.DONE and i.result_image is not None
        ]
        if not items:
            QMessageBox.information(self, "导出", "还没有成功处理完成的图片。")
            return
        self._export_items(items, single_dialog=len(items) == 1)

    def _export_items(self, items: list, *, single_dialog: bool) -> None:
        if not items:
            return
        fmt_id = get_export_format()
        custom_ext = get_export_custom_ext()
        _pfmt, suffix, _alpha = resolve_export_format(fmt_id, custom_ext)
        filt = file_filter_for_format(fmt_id, custom_ext)

        if single_dialog and len(items) == 1:
            item = items[0]
            suggested = f"{self._export_prefix}{item.source_path.stem}{suffix}"
            path, _ = QFileDialog.getSaveFileName(
                self, "导出图片", suggested, filt
            )
            if not path:
                return
            try:
                dest = export_image(
                    item.result_image,
                    path,
                    fmt_id=fmt_id,
                    custom_ext=custom_ext,
                    prefix="",
                )
                self.statusBar().showMessage(f"已保存: {dest}")
            except Exception as exc:
                QMessageBox.warning(self, "导出失败", friendly_error(exc))
            return

        folder = QFileDialog.getExistingDirectory(self, "选择导出文件夹")
        if not folder:
            return
        ok = 0
        errors = 0
        for item in items:
            try:
                export_image(
                    item.result_image,
                    Path(folder),
                    fmt_id=fmt_id,
                    custom_ext=custom_ext,
                    prefix=self._export_prefix,
                    source_name=item.source_path.name,
                )
                ok += 1
            except Exception:
                errors += 1
        self.statusBar().showMessage(
            f"已导出 {ok} 张到 {folder}"
            + (f"（失败 {errors}）" if errors else "")
        )

    @Slot()
    def clear_session(self) -> None:
        """Clear selected items (or the only image when session has one)."""
        if self.session.is_busy():
            QMessageBox.information(self, "请稍候", "处理中无法清除。")
            return
        removed, msg = self.session.clear_selected()
        self.statusBar().showMessage(msg)
        if removed <= 0:
            if self.session.count() > 1:
                QMessageBox.information(
                    self,
                    "清除选中",
                    "请先勾选要清除的图片。\n可在底部使用「全选」后再清除。",
                )
            return
        self.workspace.set_items(self.session.items)
        if self.session.count() == 0:
            self.model_label.setText("本机 · 就绪")
        self._refresh_chrome()

    @Slot()
    def _on_escape(self) -> None:
        # Settings: do NOT exit on Esc — users often press Esc while exploring
        # dropdowns or when unsure; only「返回」leaves settings (Edge-like safety).
        if self.is_settings_open():
            focus = QApplication.focusWidget()
            # Close open combo popup / clear edit focus first
            if focus is not None:
                focus.clearFocus()
            self.statusBar().showMessage("仍在设置中 — 请点左上角「← 返回」回到主界面")
            return
        # close lightbox if open
        if self.workspace.stack.currentWidget() is self.workspace.lightbox:
            if hasattr(self.workspace, "close_lightbox"):
                self.workspace.close_lightbox()
            else:
                self.workspace._close_lightbox()  # noqa: SLF001
            return
        if not self.session.is_busy() and self.session.count() > 0:
            self.clear_session()

    def _lightbox_nav(self, delta: int) -> None:
        if self.is_settings_open():
            return
        if hasattr(self.workspace, "navigate_lightbox"):
            self.workspace.navigate_lightbox(delta)
        elif self.workspace.stack.currentWidget() is self.workspace.lightbox:
            self.workspace._on_lightbox_nav(delta)  # noqa: SLF001

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        # Copy hotkey → result (backup if shortcut/filter miss)
        if not event.isAutoRepeat() and sequence_matches_event(
            get_hotkey("copy"), event
        ):
            self.copy_result()
            event.accept()
            return
        # Space hold → original (single preview only); release restores
        if (
            event.key() == Qt.Key.Key_Space
            and not event.isAutoRepeat()
            and not self.is_settings_open()
        ):
            self.workspace.set_hold_peek(True)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.workspace.set_hold_peek(False)
            event.accept()
            return
        super().keyReleaseEvent(event)

    @Slot(str)
    def _on_warmup(self, model: str) -> None:
        if not self.session.is_busy() and self.session.count() == 0:
            self.model_label.setText(f"本机 · {model}")
        if not self.session.is_busy():
            self.statusBar().showMessage(f"模型已就绪: {model}")
        # Refresh 已下载 marks if settings page is open
        if hasattr(self.settings_page, "_refresh_model_combo_labels"):
            self.settings_page._refresh_model_combo_labels()
            self.settings_page._refresh_model_help()

    @Slot(str)
    def _on_warmup_failed(self, message: str) -> None:
        if not self.session.is_busy() and self.session.count() == 0:
            self.model_label.setText(f"本机 · {get_model()}")
        # Keep message visible longer — download failures are common
        self.statusBar().showMessage(
            f"模型未就绪: {message[:120]}（导入图片时会再试）",
            12000,
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.session.is_busy():
            self.statusBar().showMessage("等待处理结束…")
            self.session.wait_worker(8000)
        if self._warmup_thread and self._warmup_thread.isRunning():
            self._warmup_thread.wait(1500)
        self.session.clear(force=True)
        super().closeEvent(event)


class _CopyHotkeyFilter(QObject):
    """Catch the rebindable copy hotkey app-wide when child widgets hold focus."""

    def __init__(self, main: MainWindow) -> None:
        super().__init__(main)
        self._main = main

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() != QEvent.Type.KeyPress:
            return False
        if not isinstance(event, QKeyEvent):
            return False
        if event.isAutoRepeat():
            return False
        if not sequence_matches_event(get_hotkey("copy"), event):
            return False
        # Don't steal while settings are open (text fields / key capture)
        if self._main.is_settings_open():
            return False
        self._main.copy_result()
        return True


class _WarmupThread(QThread):
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, engine: LocalRembgEngine) -> None:
        super().__init__()
        self.engine = engine

    def run(self) -> None:
        try:
            self.engine.warmup()
            self.done.emit(self.engine.model_name)
        except Exception as exc:
            self.failed.emit(friendly_error(exc))
