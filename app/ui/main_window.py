from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, Signal, Slot, QObject, QEvent
from PySide6.QtGui import QAction, QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
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
from app.services.hotkeys import (
    HOLD_HOTKEY_IDS,
    get_hotkey,
    sequence_matches_event,
)
from app.services.image_io import load_preview_image
from app.services.folder_watch import FolderWatchService
from app.services.settings import (
    get_alpha_matting,
    get_export_custom_ext,
    get_export_format,
    get_export_prefix,
    get_model,
    get_prefer_accel,
    get_theme,
    get_watch_archive_sources,
    get_watch_dir,
    get_watch_enabled,
    get_watch_output_dir,
    get_watch_process_existing,
    get_watch_recursive,
    get_watch_tray,
)
from app.session.batch_session import BatchSession
from app.session.limits import MAX_DROP, MAX_SESSION
from app.session.models import ItemStatus
from app.ui.errors import friendly_error
from app.ui.mask_editor import MaskEditorDialog
from app.ui.settings_dialog import SettingsPage
from app.ui.theme import build_stylesheet, resolve_theme
from app.ui.widgets import (
    SlideClearButton,
    SlideExportButton,
    SlideOpenButton,
    SlideRepairButton,
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
            prefer_accel=get_prefer_accel(),
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
        self.workspace.reprocess_requested.connect(self._on_reprocess_requested)
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

        self.btn_repair = SlideRepairButton()
        self.btn_repair.setEnabled(False)
        self.btn_repair.clicked.connect(self.repair_current_result)

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
        actions.addWidget(self.btn_repair, 0, Qt.AlignmentFlag.AlignVCenter)
        actions.addWidget(self.btn_export_sel, 0, Qt.AlignmentFlag.AlignVCenter)
        actions.addWidget(self.btn_save, 0, Qt.AlignmentFlag.AlignVCenter)
        bottom.addWidget(actions_host)

        # Watch status only (no static foot slogan)
        self.lbl_watch = QLabel("")
        self.lbl_watch.setObjectName("WatchStatusLabel")
        self.lbl_watch.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_watch.setWordWrap(True)
        self.lbl_watch.hide()
        bottom.addWidget(self.lbl_watch)

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
        self.settings_page.prefer_accel_changed.connect(self._on_prefer_accel_changed)
        self.settings_page.watch_config_changed.connect(self._apply_folder_watch)
        self.settings_page.watch_pause_toggled.connect(self._on_watch_pause_toggled)
        self.settings_page.watch_clear_queue.connect(self._on_watch_clear_queue)
        self.settings_page.watch_open_output.connect(self._on_watch_open_output)
        self.settings_page.watch_open_fail.connect(self._on_watch_open_fail)
        self.settings_page.watch_retry_failed.connect(self._on_watch_retry_failed)
        self.settings_page.hotkeys_changed.connect(self.reload_hotkeys)
        self.root_stack.addWidget(self.settings_page)

        self._repair_page: Optional[MaskEditorDialog] = None
        self._repair_item_id: Optional[str] = None
        self._force_quit = False

        # F13 folder watch (hot folder) — does not fill main grid
        self.folder_watch = FolderWatchService(
            self.engine,
            self,
            get_export_fmt=self._watch_export_fmt,
        )
        self.folder_watch.status_changed.connect(self._on_watch_status)
        self.folder_watch.stats_changed.connect(self._on_watch_stats)
        self.folder_watch.enabled_changed.connect(self._refresh_watch_badge)
        self.folder_watch.enabled_changed.connect(self._sync_tray_visibility)
        self.folder_watch.paused_changed.connect(self._on_watch_paused_changed)

        self._setup_system_tray()

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("准备就绪")

        self.session.items_changed.connect(self._on_items_changed)
        self.session.item_updated.connect(self._on_item_updated)
        self.session.busy_changed.connect(self._on_busy_changed)
        self.session.status_message.connect(self.statusBar().showMessage)
        self.session.model_name_changed.connect(self._on_model_name)

        # Restore watch if user left it enabled
        from PySide6.QtCore import QTimer

        QTimer.singleShot(600, self._apply_folder_watch)

        self._apply_theme()

        app = QApplication.instance()
        if app is not None:
            app.styleHints().colorSchemeChanged.connect(self._on_system_scheme_changed)

        # User-rebindable hotkeys (Valorant-style); hold keys via keyPress/Release
        self._hotkey_shortcuts: dict[str, QShortcut] = {}
        self._hotkey_slots = {
            "open": self.open_files,
            "export": self.export_smart,
            "copy": self.copy_result,
            "paste": self.paste_from_clipboard,
            "settings": self.open_settings,
            "escape": self._on_escape,
            "lightbox_prev": lambda: self._lightbox_nav(-1),
            "lightbox_next": lambda: self._lightbox_nav(1),
            # peek_original: hold behavior — see keyPressEvent / keyReleaseEvent
        }
        self.reload_hotkeys()

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
        """Load rebindable shortcuts from settings (including Esc / 灯箱方向键)."""
        for aid, slot in self._hotkey_slots.items():
            if aid in HOLD_HOTKEY_IDS:
                continue
            seq = get_hotkey(aid)
            sc = self._hotkey_shortcuts.get(aid)
            if sc is None:
                sc = QShortcut(self)
                # Esc: WindowShortcut so combo popups can use Esc first;
                # others: ApplicationShortcut for global reach
                if aid == "escape":
                    sc.setContext(Qt.ShortcutContext.WindowShortcut)
                else:
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
        for attr in ("btn_settings", "btn_open", "btn_clear", "btn_repair", "btn_save"):
            btn = getattr(self, attr, None)
            if btn is not None and hasattr(btn, "apply_theme_colors"):
                btn.apply_theme_colors(**capsule_kwargs)
        # Settings page back button (created with settings_page)
        if hasattr(self, "settings_page") and hasattr(self.settings_page, "btn_back"):
            back = self.settings_page.btn_back
            if hasattr(back, "apply_theme_colors"):
                back.apply_theme_colors(**capsule_kwargs)
        # Repair page back button (created on demand)
        if self._repair_page is not None and hasattr(
            self._repair_page, "apply_theme_colors"
        ):
            self._repair_page.apply_theme_colors(**capsule_kwargs)
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

    def is_repair_open(self) -> bool:
        return (
            self._repair_page is not None
            and self.root_stack.currentWidget() is self._repair_page
        )

    def _set_main_shortcuts_enabled(self, enabled: bool) -> None:
        """Disable main-app shortcuts while settings is open (avoid accidental exit)."""
        for aid, sc in self._hotkey_shortcuts.items():
            if aid == "escape":
                # Always on — handler no-ops exit while settings is open
                sc.setEnabled(not sc.key().isEmpty())
                continue
            if enabled:
                sc.setEnabled(not sc.key().isEmpty())
            else:
                sc.setEnabled(False)
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
                "设置 — 左侧点分类 · 改完点「返回」或按 Esc 回到主界面"
            )

    @Slot()
    def close_settings(self) -> None:
        self.root_stack.setCurrentIndex(0)
        self._set_main_shortcuts_enabled(True)

    @Slot(str, str)
    def _on_reprocess_requested(self, item_id: str, model_id: str) -> None:
        """Multi-grid right-click: re-run one image with a downloaded model."""
        ok, msg = self.session.reprocess_item(item_id, model_id)
        if ok:
            # Reflect engine model in chrome (settings default unchanged)
            self.model_label.setText(f"本机 · {model_id}")
            self._refresh_chrome()
        elif msg:
            self.statusBar().showMessage(msg, 5000)

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

    @Slot(bool)
    def _on_prefer_accel_changed(self, enabled: bool) -> None:
        """F14: soft accel preference — never blocks CPU-only machines."""
        from app.engines.runtime_accel import detect_accel

        self.engine.set_prefer_accel(enabled)
        status = detect_accel()
        if enabled:
            if status.available:
                tip = f"已开启更快处理（{status.summary}）。下次加载模型时生效。"
            else:
                tip = (
                    "已开启更快处理，但当前电脑未检测到加速组件，"
                    "将继续使用普通模式。"
                )
        else:
            tip = "已关闭更快处理，使用普通模式。"
        self.statusBar().showMessage(tip)
        # Reload session with new providers when idle
        if not self.session.is_busy():
            self._start_model_warmup()

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
        repair_item = self._resolve_copy_item()
        self.btn_repair.setEnabled(
            repair_item is not None and repair_item.result_image is not None
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
        if not busy:
            self.folder_watch.notify_engine_idle()

    def _watch_export_fmt(self):
        return (
            get_export_format(),
            get_export_custom_ext(),
            get_export_prefix(),
        )

    @Slot()
    def _apply_folder_watch(self) -> None:
        """Start/stop F13 watch from saved settings."""
        enabled = get_watch_enabled()
        watch = get_watch_dir().strip()
        output = get_watch_output_dir().strip()
        process_existing = get_watch_process_existing()
        recursive = get_watch_recursive()
        archive = get_watch_archive_sources()

        if not enabled:
            if self.folder_watch.is_enabled:
                self.folder_watch.stop()
            if hasattr(self.settings_page, "set_watch_runtime_status"):
                self.settings_page.set_watch_runtime_status("监视已关闭")
            self._refresh_watch_badge()
            self._sync_tray_visibility()
            return

        from pathlib import Path

        self.folder_watch.configure(
            watch_dir=Path(watch) if watch else None,
            output_dir=Path(output) if output else None,
            process_existing=process_existing,
            recursive=recursive,
            archive_sources=archive,
        )
        # Restart cleanly when applying
        if self.folder_watch.is_enabled:
            self.folder_watch.stop()
        ok, msg = self.folder_watch.start()
        if not ok:
            from app.services.settings import set_watch_enabled

            set_watch_enabled(False)
            if hasattr(self.settings_page, "set_watch_runtime_status"):
                self.settings_page.set_watch_runtime_status(msg)
            if hasattr(self.settings_page, "_sync_watch_fields"):
                self.settings_page._sync_watch_fields()
            self.statusBar().showMessage(msg, 8000)
            return
        if hasattr(self.settings_page, "set_watch_runtime_status"):
            self.settings_page.set_watch_runtime_status(self.folder_watch.status_text())
        self.statusBar().showMessage(self.folder_watch.status_text(), 6000)
        self._refresh_watch_badge()
        self._sync_tray_visibility()

    def _setup_system_tray(self) -> None:
        self.tray: Optional[QSystemTrayIcon] = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("Peel · 文件夹监视")
        menu = QMenu()
        act_show = QAction("显示主窗口", self)
        act_show.triggered.connect(self._show_from_tray)
        act_pause = QAction("暂停/继续监视", self)
        act_pause.triggered.connect(self._on_watch_pause_toggled)
        act_quit = QAction("退出", self)
        act_quit.triggered.connect(self._quit_from_tray)
        menu.addAction(act_show)
        menu.addAction(act_pause)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)

    def _sync_tray_visibility(self, *_args) -> None:
        if self.tray is None:
            return
        if self.folder_watch.is_enabled and get_watch_tray():
            self.tray.show()
            self.tray.setToolTip(self.folder_watch.short_badge_text() or "Peel 监视中")
        else:
            self.tray.hide()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self) -> None:
        self._force_quit = True
        self.close()

    def _on_tray_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_from_tray()

    def _refresh_watch_badge(self, *_args) -> None:
        if not hasattr(self, "lbl_watch"):
            return
        if self.folder_watch.is_enabled:
            text = self.folder_watch.short_badge_text()
            self.lbl_watch.setText(text)
            self.lbl_watch.setVisible(bool(text))
            if hasattr(self.settings_page, "set_watch_pause_label"):
                self.settings_page.set_watch_pause_label(self.folder_watch.is_paused)
        else:
            self.lbl_watch.hide()
            self.lbl_watch.clear()

    @Slot(str)
    def _on_watch_status(self, text: str) -> None:
        if text:
            self.statusBar().showMessage(text)
        if hasattr(self.settings_page, "set_watch_runtime_status"):
            self.settings_page.set_watch_runtime_status(text)
        self._refresh_watch_badge()

    @Slot(int, int, int)
    def _on_watch_stats(self, pending: int, success: int, failed: int) -> None:
        del pending, success, failed
        if self.folder_watch.is_enabled:
            self.statusBar().showMessage(self.folder_watch.status_text())
        self._refresh_watch_badge()

    @Slot(bool)
    def _on_watch_paused_changed(self, paused: bool) -> None:
        if hasattr(self.settings_page, "set_watch_pause_label"):
            self.settings_page.set_watch_pause_label(paused)
        self._refresh_watch_badge()

    @Slot()
    def _on_watch_pause_toggled(self) -> None:
        if not self.folder_watch.is_enabled:
            self.statusBar().showMessage("请先开启文件夹监视并点应用", 4000)
            return
        self.folder_watch.set_paused(not self.folder_watch.is_paused)

    @Slot()
    def _on_watch_clear_queue(self) -> None:
        if not self.folder_watch.is_enabled:
            self.statusBar().showMessage("监视未开启", 3000)
            return
        n = self.folder_watch.clear_pending_queue()
        # clear_pending_queue re-scans and may re-queue unprocessed folder images
        self.statusBar().showMessage(
            self.folder_watch.status_text()
            or f"已清空待处理 {n} 项",
            6000,
        )
        if hasattr(self.settings_page, "set_watch_runtime_status"):
            self.settings_page.set_watch_runtime_status(
                self.folder_watch.status_text()
            )
        self._refresh_watch_badge()

    @Slot()
    def _on_watch_retry_failed(self) -> None:
        if not self.folder_watch.is_enabled:
            self.statusBar().showMessage("请先开启文件夹监视并点应用", 4000)
            return
        n = self.folder_watch.retry_failed()
        if n:
            self.statusBar().showMessage(f"已重新排队失败 {n} 项", 5000)
        else:
            self.statusBar().showMessage("没有可重试的失败项（或源文件已不在）", 5000)

    @Slot()
    def _on_watch_open_output(self) -> None:
        path = self.folder_watch.open_output_dir()
        if path is None:
            # try from settings even if stopped
            w = get_watch_dir().strip()
            if not w:
                self.statusBar().showMessage("尚未设置监视/输出文件夹", 4000)
                return
            from pathlib import Path

            o = get_watch_output_dir().strip()
            path = (
                Path(o)
                if o
                else FolderWatchService.default_output_dir(Path(w))
            )
            path.mkdir(parents=True, exist_ok=True)
        self._reveal_in_explorer(path)

    @Slot()
    def _on_watch_open_fail(self) -> None:
        path = self.folder_watch.open_fail_dir()
        if path is None:
            w = get_watch_dir().strip()
            if not w:
                self.statusBar().showMessage("尚未设置监视文件夹", 4000)
                return
            from pathlib import Path

            o = get_watch_output_dir().strip()
            out = (
                Path(o)
                if o
                else FolderWatchService.default_output_dir(Path(w))
            )
            path = FolderWatchService.fail_dir_for_output(out)
            path.mkdir(parents=True, exist_ok=True)
        self._reveal_in_explorer(path)

    def _reveal_in_explorer(self, path) -> None:
        import os
        import subprocess
        import sys

        p = str(path)
        try:
            if sys.platform.startswith("win"):
                os.startfile(p)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", p])
            else:
                subprocess.Popen(["xdg-open", p])
        except Exception as exc:
            self.statusBar().showMessage(f"无法打开文件夹：{exc}", 5000)

    @Slot(str)
    def _on_model_name(self, name: str) -> None:
        device = getattr(self.engine, "device_label", None) or "普通模式"
        self.model_label.setText(f"本机 · {name} · {device}")

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

    @Slot()
    def repair_current_result(self) -> None:
        if self.is_repair_open():
            return
        item = self._resolve_copy_item()
        if item is None or item.result_image is None:
            QMessageBox.information(self, "修补", "请先打开一张已经处理完成的图片。")
            return
        try:
            original = load_preview_image(item.source_path).convert("RGBA")
        except Exception as exc:
            QMessageBox.warning(self, "修补", f"无法读取原图：{friendly_error(exc)}")
            return
        if original.size != item.result_image.size:
            QMessageBox.warning(self, "修补", "原图与当前结果尺寸不一致，无法安全修补。")
            return
        page = MaskEditorDialog(original, item.result_image, item.name, self.root_stack)
        page.completed.connect(self._finish_repair)
        page.cancelled.connect(self._cancel_repair)
        # Match capsule theme (back button is painted, not QSS-only)
        colors = resolve_theme(self._theme_pref)
        page.apply_theme_colors(
            bg=colors.button_bg,
            border=colors.button_border,
            hover=colors.button_hover,
            pressed=colors.button_pressed,
            disabled_bg=colors.button_disabled_bg,
            primary=colors.primary,
            text=colors.text,
            disabled_text=colors.button_disabled_text,
        )
        self._repair_page = page
        self._repair_item_id = item.id
        self.root_stack.addWidget(page)
        self._set_main_shortcuts_enabled(False)
        self.root_stack.setCurrentWidget(page)
        page.canvas.setFocus(Qt.FocusReason.OtherFocusReason)
        self.statusBar().showMessage("修补中：完成后将应用到当前图片")

    @Slot()
    def _finish_repair(self) -> None:
        page = self._repair_page
        item_id = self._repair_item_id
        edited = page.edited_image if page is not None else None
        if item_id is not None and edited is not None:
            if self.session.replace_result_image(item_id, edited):
                self.statusBar().showMessage(
                    "已应用修补，可继续导出、复制或拖出结果", 5000
                )
        self._close_repair_page()

    @Slot()
    def _cancel_repair(self) -> None:
        self.statusBar().showMessage("已取消修补，原结果未改变", 4000)
        self._close_repair_page()

    def _close_repair_page(self) -> None:
        page = self._repair_page
        self._repair_page = None
        self._repair_item_id = None
        self.root_stack.setCurrentIndex(0)
        self._set_main_shortcuts_enabled(True)
        if page is not None:
            self.root_stack.removeWidget(page)
            page.deleteLater()

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
        """
        「返回上一级」— 按界面栈回退一层。

        层级（深 → 浅）:
          修补页（有草稿选区先清选区）→ 主界面
          设置页 → 主界面（与左上角「返回」相同）
          灯箱 → 多图网格
          主界面 → 已在最顶层
        """
        # 1) Repair is above main
        if self.is_repair_open():
            assert self._repair_page is not None
            if self._repair_page.canvas.has_draft_selection:
                self._repair_page.canvas.clear_selection()
                self.statusBar().showMessage("已清除选区", 2000)
            else:
                self._repair_page.cancel_editing()
            return

        # 2) Settings → main (same as 返回)
        if self.is_settings_open():
            focus = QApplication.focusWidget()
            if focus is not None:
                focus.clearFocus()
            self.close_settings()
            return

        # 3) Lightbox → multi grid
        if self.workspace.stack.currentWidget() is self.workspace.lightbox:
            if hasattr(self.workspace, "close_lightbox"):
                self.workspace.close_lightbox()
            else:
                self.workspace._close_lightbox()  # noqa: SLF001
            self.statusBar().showMessage("已返回网格", 2000)
            return

        # 4) Already at main level
        if self.session.count() > 0:
            self.statusBar().showMessage("已在主界面", 2000)

    def _lightbox_nav(self, delta: int) -> None:
        if self.is_settings_open() or self.is_repair_open():
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
        # Hold-to-peek original (default Space; rebindable as peek_original)
        if (
            not event.isAutoRepeat()
            and sequence_matches_event(get_hotkey("peek_original"), event)
            and not self.is_settings_open()
            and not self.is_repair_open()
        ):
            self.workspace.set_hold_peek(True)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if (
            not event.isAutoRepeat()
            and sequence_matches_event(get_hotkey("peek_original"), event)
            and not self.is_repair_open()
        ):
            self.workspace.set_hold_peek(False)
            event.accept()
            return
        super().keyReleaseEvent(event)

    @Slot(str)
    def _on_warmup(self, model: str) -> None:
        device = getattr(self.engine, "device_label", None) or "普通模式"
        if not self.session.is_busy() and self.session.count() == 0:
            self.model_label.setText(f"本机 · {model} · {device}")
        # Refresh 已下载 marks if settings page is open
        if hasattr(self.settings_page, "_refresh_model_combo_labels"):
            self.settings_page._refresh_model_combo_labels()
            self.settings_page._refresh_model_help()
        if hasattr(self.settings_page, "_refresh_accel_ui"):
            self.settings_page._refresh_accel_ui()

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
        # Watch + tray: hide to tray instead of quit (unless tray quit / force)
        if (
            not getattr(self, "_force_quit", False)
            and getattr(self, "folder_watch", None) is not None
            and self.folder_watch.is_enabled
            and get_watch_tray()
            and self.tray is not None
            and self.tray.isVisible()
        ):
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "Peel",
                "文件夹监视仍在后台运行。双击托盘图标可打开窗口。",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
            return

        if hasattr(self, "folder_watch") and self.folder_watch.is_enabled:
            self.folder_watch.stop()
        if self.tray is not None:
            self.tray.hide()
        if self.session.is_busy():
            self.statusBar().showMessage("等待处理结束…")
            self.session.wait_worker(8000)
        if getattr(self, "folder_watch", None) is not None and self.folder_watch.is_busy():
            w = self.folder_watch._worker
            if w is not None and w.isRunning():
                w.wait(8000)
        wt = getattr(self, "_warmup_thread", None)
        if wt is not None and wt.isRunning():
            wt.wait(1500)
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
