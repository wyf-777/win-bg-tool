"""Edge-style full-window settings: left nav + right detail."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.engines.local_rembg import delete_incomplete_downloads
from app.engines.models_catalog import (
    MODEL_CATALOG,
    catalog_disk_snapshot,
    delete_model_files,
    get_model_info,
    model_combo_label,
    pick_fallback_model_id,
    product_default_model_id,
)
from app.engines.runtime_accel import detect_accel
from app.services.export import EXPORT_FORMATS
from app.services.hotkeys import (
    HOTKEY_ORDER,
    action_description,
    action_label,
    get_hotkey,
    reset_hotkeys,
    set_hotkey,
)
from app.ui.key_capture import KeyCaptureButton
from app.ui.widgets import SlideBackButton
from app.services.folder_watch import (
    DEFAULT_ARCHIVE_SUBDIR,
    DEFAULT_FAIL_SUBDIR,
    DEFAULT_OUTPUT_SUBDIR,
    FolderWatchService,
)
from app.services.settings import (
    get_alpha_matting,
    get_export_custom_ext,
    get_export_format,
    get_export_prefix,
    get_export_prefix_enabled,
    get_effective_export_prefix,
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
    set_alpha_matting,
    set_export_custom_ext,
    set_export_format,
    set_export_prefix,
    set_export_prefix_enabled,
    set_model,
    set_prefer_accel,
    set_theme,
    set_watch_archive_sources,
    set_watch_dir,
    set_watch_enabled,
    set_watch_output_dir,
    set_watch_process_existing,
    set_watch_recursive,
    set_watch_tray,
)

__all__ = ["SettingsPage", "SettingsDialog"]


class SettingsPage(QWidget):
    """
    Full-window settings panel (fills parent).
    Left: category list. Right: detail for selected category.
    """

    back_requested = Signal()
    theme_changed = Signal(str)
    model_changed = Signal(str)
    export_format_changed = Signal(str)  # format id
    export_prefix_changed = Signal(str)  # effective prefix used for naming
    alpha_matting_changed = Signal(bool)
    prefer_accel_changed = Signal(bool)  # F14 soft GPU preference
    watch_config_changed = Signal()  # F13 apply/start/stop from settings
    watch_pause_toggled = Signal()  # pause / resume
    watch_clear_queue = Signal()
    watch_open_input = Signal()  # open watch/import folder
    watch_open_output = Signal()
    watch_open_fail = Signal()
    watch_retry_failed = Signal()
    hotkeys_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsPage")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # model_id -> (status, size_bytes); filled by _model_disk_snapshot
        self._model_disk_cache: dict[str, tuple[str, int]] | None = None
        self._cached_applied_model: str = ""
        self._accel_status_cache = None  # detect_accel() result, process-stable

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ────────────────────────────────────────
        top = QFrame()
        top.setObjectName("SettingsTopBar")
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(16, 12, 16, 12)
        top_l.setSpacing(12)

        self.btn_back = SlideBackButton()
        self.btn_back.clicked.connect(self.back_requested.emit)

        top_l.addWidget(self.btn_back)
        top_l.addStretch(1)
        root.addWidget(top)

        # ── Body: nav | detail ─────────────────────────────
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setObjectName("SettingsNav")
        self.nav.setFixedWidth(200)
        self.nav.setSpacing(2)
        # Prevent accidental empty selection (row -1) which can confuse navigation
        self.nav.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        for name in ("外观", "模型选择", "导出", "文件夹", "快捷键"):
            item = QListWidgetItem(name)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            self.nav.addItem(item)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._on_nav)
        body.addWidget(self.nav)

        self.stack = QStackedWidget()
        self.stack.setObjectName("SettingsStack")
        self.stack.addWidget(self._build_appearance_page())
        self.stack.addWidget(self._build_model_page())
        self.stack.addWidget(self._build_export_page())
        self.stack.addWidget(self._build_watch_page())
        self.stack.addWidget(self._build_hotkeys_page())
        body.addWidget(self.stack, 1)

        body_host = QWidget()
        body_host.setLayout(body)
        root.addWidget(body_host, 1)

        self._refresh_model_help()
        self._update_custom_ext_visible()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_from_settings()

    def _sync_from_settings(self) -> None:
        idx = max(0, self.theme_combo.findData(get_theme()))
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(idx)
        self.theme_combo.blockSignals(False)

        self._invalidate_model_disk_cache()
        self._cached_applied_model = get_model()
        self._refresh_model_combo_labels(force_disk=True)
        midx = max(0, self.model_combo.findData(self._cached_applied_model))
        self.model_combo.blockSignals(True)
        if self.model_combo.currentIndex() != midx:
            self.model_combo.setCurrentIndex(midx)
        self.model_combo.blockSignals(False)
        self._refresh_model_help(force_disk=False)

        self.chk_alpha.blockSignals(True)
        self.chk_alpha.setChecked(get_alpha_matting())
        self.chk_alpha.blockSignals(False)

        self._refresh_accel_ui()

        fidx = max(0, self.format_combo.findData(get_export_format()))
        self.format_combo.blockSignals(True)
        self.format_combo.setCurrentIndex(fidx)
        self.format_combo.blockSignals(False)

        self.custom_ext_edit.blockSignals(True)
        self.custom_ext_edit.setText(get_export_custom_ext())
        self.custom_ext_edit.blockSignals(False)
        self._update_custom_ext_visible()

        self.prefix_edit.blockSignals(True)
        self.prefix_edit.setText(get_export_prefix())
        self.prefix_edit.blockSignals(False)
        self.chk_prefix_enabled.blockSignals(True)
        self.chk_prefix_enabled.setChecked(get_export_prefix_enabled())
        self.chk_prefix_enabled.blockSignals(False)
        self._sync_prefix_enabled_ui()

        self._sync_watch_fields()
        self._refresh_hotkey_buttons()

    def _on_nav(self, row: int) -> None:
        if row < 0:
            # Restore a valid selection if list cleared focus/selection
            self.nav.blockSignals(True)
            self.nav.setCurrentRow(self.stack.currentIndex())
            self.nav.blockSignals(False)
            return
        self.stack.setCurrentIndex(row)

    def _wrap_page(self, *widgets: QWidget) -> QWidget:
        """Right-side detail with scroll — shrink window scrolls instead of crushing."""
        page = QWidget()
        page.setObjectName("SettingsDetailPage")
        page.setMinimumWidth(320)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 20, 28, 20)
        lay.setSpacing(16)
        for w in widgets:
            lay.addWidget(w)
        lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("SettingsDetailScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(page)
        scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        return scroll

    def _hint(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("SettingsHint")
        lab.setWordWrap(True)
        lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return lab

    def _build_appearance_page(self) -> QWidget:
        form_host = QWidget()
        form = QFormLayout(form_host)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(14)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.theme_combo = QComboBox()
        self.theme_combo.setToolTip("仅影响本程序，不会修改 Windows 系统主题")
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        self.theme_combo.addItem("跟随系统", "system")
        self.theme_combo.currentIndexChanged.connect(self._on_theme_combo)

        form.addRow("主题颜色", self.theme_combo)
        return self._wrap_page(form_host)

    def _build_model_page(self) -> QWidget:
        """模型选择 — 稳定布局：切换模型时不因文案长短把右侧挤乱。"""
        block = QWidget()
        block.setObjectName("ModelSettingsBlock")
        lay = QVBoxLayout(block)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(12)
        lab = QLabel("默认模型")
        lab.setObjectName("SettingsFieldLabel")
        lab.setMinimumWidth(64)
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(160)
        self.model_combo.setMaximumHeight(36)
        # 固定按内容长度策略，避免「已下载·长名称」把整页撑乱
        self.model_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.model_combo.setMinimumContentsLength(22)
        self.model_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.model_combo.setToolTip(
            "仅浏览说明，不会立刻下载或切换。"
            "已下载=可点「应用」；未下载=需确认后下载；可「卸载」释放磁盘。"
        )
        for info in MODEL_CATALOG:
            self.model_combo.addItem(model_combo_label(info), info.id)
        # 下拉只预览，不写设置、不触发下载
        self.model_combo.currentIndexChanged.connect(self._on_model_combo_preview)
        row.addWidget(lab, 0)
        row.addWidget(self.model_combo, 1)
        lay.addLayout(row)

        self.model_dl_hint = self._hint(
            "下拉只用于查看与选择目标模型，不会自动下载。"
            "未下载时请点「下载并应用」并确认；已下载可「应用为默认」或「卸载」。"
            "中途退出会保留 .part，可续传或点「清理未完成下载」。"
        )
        lay.addWidget(self.model_dl_hint)

        # 与监视页操作行一致：等高 36、三格等分；Fixed 高度避免改文案时整页重排
        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        action_row.setContentsMargins(0, 0, 0, 0)

        self.btn_apply_model = QPushButton("应用为默认")
        self.btn_apply_model.setObjectName("PrimaryBtn")
        self.btn_apply_model.setToolTip(
            "把当前下拉选中的模型设为默认。"
            "若本地没有文件，会先弹出确认再下载。"
        )
        self.btn_apply_model.clicked.connect(self._on_apply_or_download_model)

        self.btn_uninstall_model = QPushButton("卸载本地")
        self.btn_uninstall_model.setObjectName("ActionBtn")
        self.btn_uninstall_model.setToolTip(
            "删除该模型在 models 目录下的 .onnx（及未完成 .part），释放磁盘空间。"
            "若正在使用该模型，会自动改用其它已下载模型。"
        )
        self.btn_uninstall_model.clicked.connect(self._on_uninstall_model)

        self.btn_clear_partial = QPushButton("清理未完成")
        self.btn_clear_partial.setObjectName("ActionBtn")
        self.btn_clear_partial.setToolTip(
            "删除 models 目录里所有 .part 半成品，下次将从头下载"
        )
        self.btn_clear_partial.clicked.connect(self._on_clear_partial_downloads)

        for btn in (
            self.btn_apply_model,
            self.btn_uninstall_model,
            self.btn_clear_partial,
        ):
            btn.setFixedHeight(36)
            btn.setMinimumWidth(100)
            # Expanding 宽度等分；高度固定，避免 setText 触发整页 layout 抖动
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            action_row.addWidget(btn, 1)

        lay.addLayout(action_row)

        skill_cap = QLabel("擅长")
        skill_cap.setObjectName("SettingsFieldLabel")
        lay.addWidget(skill_cap)

        # 固定高度 QTextEdit：切换长短文案时不改整体布局高度
        self.model_skill = self._make_model_body_box(min_height=88)
        lay.addWidget(self.model_skill)

        note_cap = QLabel("说明")
        note_cap.setObjectName("SettingsFieldLabel")
        lay.addWidget(note_cap)

        self.model_note = self._make_model_body_box(min_height=72)
        lay.addWidget(self.model_note)

        # 状态单独一行，避免塞进说明块导致高度乱跳
        self.model_status = QLabel("")
        self.model_status.setObjectName("SettingsHint")
        self.model_status.setWordWrap(True)
        self.model_status.setMinimumHeight(40)
        self.model_status.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        lay.addWidget(self.model_status)

        self.chk_alpha = QCheckBox("启用 Alpha Matting（边缘更细，更慢）")
        self.chk_alpha.toggled.connect(self._on_alpha_toggle)
        lay.addWidget(self.chk_alpha)

        # F14 — checkbox only; status line only when enabled
        self.chk_prefer_accel = QCheckBox("更快处理（有条件时用显卡加速）")
        self.chk_prefer_accel.setToolTip(
            "默认普通模式，人人可用。"
            "勾选后若本机支持会尽量加速；不支持或失败会自动用普通模式。"
        )
        self.chk_prefer_accel.toggled.connect(self._on_prefer_accel_toggle)
        lay.addWidget(self.chk_prefer_accel)

        self.accel_status = QLabel("")
        self.accel_status.setObjectName("SettingsHint")
        self.accel_status.setWordWrap(True)
        self.accel_status.setVisible(False)
        lay.addWidget(self.accel_status)

        lay.addStretch(1)
        return self._wrap_page(block)

    def _make_model_body_box(self, *, min_height: int) -> QTextEdit:
        """Stable multi-line body for model skill/note (no layout thrash)."""
        box = QTextEdit()
        box.setObjectName("SettingsBodyText")
        box.setReadOnly(True)
        box.setAcceptRichText(False)
        box.setFrameShape(QFrame.Shape.NoFrame)
        box.setFixedHeight(min_height)
        box.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        box.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        box.setTabChangesFocus(True)
        return box

    def _watch_field_label(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("SettingsFieldLabel")
        return lab

    def _watch_path_edit(self, placeholder: str) -> QLineEdit:
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setReadOnly(True)
        edit.setMinimumHeight(36)
        edit.setMinimumWidth(180)
        edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        edit.setClearButtonEnabled(False)
        return edit

    def _watch_action_btn(self, text: str, tooltip: str = "") -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("ActionBtn")
        btn.setMinimumWidth(88)
        btn.setMinimumHeight(36)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        if tooltip:
            btn.setToolTip(tooltip)
        return btn

    def _set_path_edit_text(self, edit: QLineEdit, text: str) -> None:
        """Set path text and keep caret at start so long paths aren't only showing the tail."""
        edit.setText(text or "")
        edit.setCursorPosition(0)
        edit.setToolTip(text or "")

    def _build_watch_page(self) -> QWidget:
        """F13 hot folder — clearer sectioned layout (paths / options / actions)."""
        block = QWidget()
        lay = QVBoxLayout(block)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        # ── Intro ─────────────────────────────────────────
        intro = self._hint(
            "把图片放进「监视文件夹」，会自动抠图并保存到输出文件夹。"
            "结果不占用主界面列表。"
        )
        lay.addWidget(intro)

        # Hidden checkbox kept for settings sync / apply-state logic
        self.chk_watch_enabled = QCheckBox("开启文件夹监视")
        self.chk_watch_enabled.setToolTip("由「应用 / 关闭应用」控制，一般无需手动勾选")
        self.chk_watch_enabled.setVisible(False)

        # ── Paths ─────────────────────────────────────────
        lay.addWidget(self._watch_field_label("监视文件夹（进图 / 导入）"))
        row_w = QHBoxLayout()
        row_w.setSpacing(10)
        self.edit_watch_dir = self._watch_path_edit("选择要监视的文件夹…")
        btn_w = self._watch_action_btn("浏览…", "选择监视文件夹")
        btn_w.clicked.connect(self._browse_watch_dir)
        row_w.addWidget(self.edit_watch_dir, 1)
        row_w.addWidget(btn_w, 0)
        lay.addLayout(row_w)

        lay.addWidget(self._watch_field_label("输出文件夹（结果）"))
        row_o = QHBoxLayout()
        row_o.setSpacing(10)
        self.edit_watch_output = self._watch_path_edit(
            f"默认：监视文件夹下的「{DEFAULT_OUTPUT_SUBDIR}」"
        )
        btn_o = self._watch_action_btn("浏览…", "选择输出文件夹")
        btn_o.clicked.connect(self._browse_watch_output)
        btn_o_clear = self._watch_action_btn(
            "用默认", f"恢复为 监视目录/{DEFAULT_OUTPUT_SUBDIR}"
        )
        btn_o_clear.clicked.connect(self._clear_watch_output)
        row_o.addWidget(self.edit_watch_output, 1)
        row_o.addWidget(btn_o, 0)
        row_o.addWidget(btn_o_clear, 0)
        lay.addLayout(row_o)

        # ── Options ───────────────────────────────────────
        lay.addWidget(self._watch_field_label("选项"))
        opts = QVBoxLayout()
        opts.setSpacing(8)
        opts.setContentsMargins(2, 0, 2, 0)

        self.chk_watch_existing = QCheckBox(
            "开启时重新处理夹内图片（含此前已成功记录的）"
        )
        self.chk_watch_existing.setToolTip(
            "默认开启。\n"
            "· 勾选：点应用后会排队夹内图片，并重做已成功记录的。\n"
            "· 不勾选：仍会处理「从未成功过」的图；已成功/失败记录的会跳过"
            "（失败可用「重试失败」）。\n"
            "源文件默认留在夹内，成功数增加但夹内仍有图是正常的"
            "（可勾选「成功后归档」）。"
        )
        opts.addWidget(self.chk_watch_existing)

        self.chk_watch_recursive = QCheckBox("包含子文件夹")
        self.chk_watch_recursive.setToolTip(
            "开启后会扫描子目录中的图片；结果按相对路径写入输出文件夹"
        )
        opts.addWidget(self.chk_watch_recursive)

        self.chk_watch_archive = QCheckBox(
            f"成功后把原图移到「{DEFAULT_ARCHIVE_SUBDIR}」"
        )
        self.chk_watch_archive.setToolTip(
            "抠图成功后把源文件移到监视目录下的「已处理」，避免进图夹越堆越多"
        )
        opts.addWidget(self.chk_watch_archive)

        self.chk_watch_tray = QCheckBox("监视开启时，关闭窗口最小化到托盘")
        self.chk_watch_tray.setToolTip(
            "方便后台继续监视；在托盘图标上可重新打开窗口或退出"
        )
        opts.addWidget(self.chk_watch_tray)
        lay.addLayout(opts)

        self.watch_hint = self._hint(
            f"输出默认在「{DEFAULT_OUTPUT_SUBDIR}」；失败在输出下的「失败」。"
            "清单保存在应用数据中，不会出现在导出文件夹。"
            "导出格式与前缀跟「导出」页一致。"
        )
        lay.addWidget(self.watch_hint)

        # ── Runtime status (card) ──────────────────────────
        lay.addWidget(self._watch_field_label("运行状态"))
        self.watch_status = QLabel("尚未开启监视")
        self.watch_status.setObjectName("SettingsBodyText")
        self.watch_status.setWordWrap(True)
        self.watch_status.setMinimumHeight(56)
        self.watch_status.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.watch_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.watch_status.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        lay.addWidget(self.watch_status)

        # ── Runtime controls: two rows so buttons don't crush ─
        lay.addWidget(self._watch_field_label("操作"))
        run1 = QHBoxLayout()
        run1.setSpacing(10)
        self.btn_watch_pause = self._watch_action_btn(
            "暂停", "暂停接收与处理（正在抠的一张会跑完）"
        )
        self.btn_watch_pause.clicked.connect(self._on_watch_pause_clicked)
        self.btn_watch_clear = self._watch_action_btn(
            "清空队列", "清空等待中的文件（不中断当前这一张）"
        )
        self.btn_watch_clear.clicked.connect(self._on_watch_clear_clicked)
        self.btn_watch_retry = self._watch_action_btn(
            "重试失败", "把最近失败且源文件仍在的项目重新排队"
        )
        self.btn_watch_retry.clicked.connect(lambda: self.watch_retry_failed.emit())
        run1.addWidget(self.btn_watch_pause)
        run1.addWidget(self.btn_watch_clear)
        run1.addWidget(self.btn_watch_retry)
        run1.addStretch(1)
        lay.addLayout(run1)

        run2 = QHBoxLayout()
        run2.setSpacing(10)
        self.btn_watch_open_in = self._watch_action_btn(
            "打开导入", "打开监视/导入文件夹（往这里放待抠图）"
        )
        self.btn_watch_open_in.clicked.connect(self._on_watch_open_input)
        self.btn_watch_open_out = self._watch_action_btn(
            "打开输出", "打开输出文件夹（抠图结果）"
        )
        self.btn_watch_open_out.clicked.connect(self._on_watch_open_output)
        self.btn_watch_open_fail = self._watch_action_btn(
            "打开失败", "打开失败目录（错误说明 + 源文件副本）"
        )
        self.btn_watch_open_fail.clicked.connect(self._on_watch_open_fail)
        run2.addWidget(self.btn_watch_open_in)
        run2.addWidget(self.btn_watch_open_out)
        run2.addWidget(self.btn_watch_open_fail)
        run2.addStretch(1)
        lay.addLayout(run2)

        # ── Apply / close ─────────────────────────────────
        apply_row = QHBoxLayout()
        apply_row.setContentsMargins(0, 8, 0, 0)
        apply_row.addStretch(1)
        self._watch_apply_running = False
        self.btn_watch_apply = QPushButton("应用")
        self.btn_watch_apply.setObjectName("PrimaryBtn")
        self.btn_watch_apply.setMinimumWidth(120)
        self.btn_watch_apply.setMinimumHeight(36)
        self.btn_watch_apply.setToolTip("保存设置并开启文件夹监视")
        self.btn_watch_apply.clicked.connect(self._on_watch_apply)
        apply_row.addWidget(self.btn_watch_apply)
        lay.addLayout(apply_row)

        lay.addStretch(1)
        return self._wrap_page(block)

    def _sync_watch_fields(self) -> None:
        if not hasattr(self, "chk_watch_enabled"):
            return
        self.chk_watch_enabled.blockSignals(True)
        self.chk_watch_enabled.setChecked(get_watch_enabled())
        self.chk_watch_enabled.blockSignals(False)
        self._set_path_edit_text(self.edit_watch_dir, get_watch_dir())
        self._set_path_edit_text(self.edit_watch_output, get_watch_output_dir())
        self.chk_watch_existing.blockSignals(True)
        self.chk_watch_existing.setChecked(get_watch_process_existing())
        self.chk_watch_existing.blockSignals(False)
        self.chk_watch_recursive.blockSignals(True)
        self.chk_watch_recursive.setChecked(get_watch_recursive())
        self.chk_watch_recursive.blockSignals(False)
        self.chk_watch_archive.blockSignals(True)
        self.chk_watch_archive.setChecked(get_watch_archive_sources())
        self.chk_watch_archive.blockSignals(False)
        self.chk_watch_tray.blockSignals(True)
        self.chk_watch_tray.setChecked(get_watch_tray())
        self.chk_watch_tray.blockSignals(False)
        self._update_watch_status_label()
        # Reflect actual saved enabled state until main window reports runtime
        self.set_watch_apply_state(get_watch_enabled() and bool(get_watch_dir().strip()))

    def set_watch_runtime_status(self, text: str) -> None:
        if hasattr(self, "watch_status"):
            raw = (text or "").strip() or "尚未开启监视"
            # Break long "a · b · c" status into lines for the card layout
            display = raw.replace(" · ", "\n")
            self.watch_status.setText(display)
            self.watch_status.setToolTip(raw)

    def set_watch_pause_label(self, paused: bool) -> None:
        if hasattr(self, "btn_watch_pause"):
            self.btn_watch_pause.setText("继续" if paused else "暂停")

    def set_watch_apply_state(self, running: bool) -> None:
        """Toggle primary button: 应用 ↔ 关闭应用."""
        if not hasattr(self, "btn_watch_apply"):
            return
        self._watch_apply_running = bool(running)
        if self._watch_apply_running:
            self.btn_watch_apply.setText("关闭应用")
            self.btn_watch_apply.setToolTip("关闭文件夹监视功能")
            self.chk_watch_enabled.blockSignals(True)
            self.chk_watch_enabled.setChecked(True)
            self.chk_watch_enabled.blockSignals(False)
        else:
            self.btn_watch_apply.setText("应用")
            self.btn_watch_apply.setToolTip("保存设置并开启文件夹监视")

    def _update_watch_status_label(self) -> None:
        if not hasattr(self, "watch_status"):
            return
        w = get_watch_dir()
        if get_watch_enabled() and w:
            out = get_watch_output_dir() or f"{w}\\{DEFAULT_OUTPUT_SUBDIR}"
            # Multi-line so long paths don't crush the action row
            text = f"已保存：监视开启\n导入：{w}\n输出：{out}"
        elif w:
            text = f"已保存路径；监视当前为关闭（点「应用」开启）\n导入：{w}"
        else:
            text = "选择监视文件夹后，点「应用」开启监视。"
        self.watch_status.setText(text)
        self.watch_status.setToolTip(text)

    def _browse_watch_dir(self) -> None:
        start = get_watch_dir() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "选择监视文件夹", start)
        if path:
            self._set_path_edit_text(self.edit_watch_dir, path)

    def _browse_watch_output(self) -> None:
        start = get_watch_output_dir() or get_watch_dir() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "选择输出文件夹", start)
        if path:
            self._set_path_edit_text(self.edit_watch_output, path)

    def _clear_watch_output(self) -> None:
        self._set_path_edit_text(self.edit_watch_output, "")

    def _on_watch_pause_clicked(self) -> None:
        self.watch_pause_toggled.emit()

    def _on_watch_clear_clicked(self) -> None:
        self.watch_clear_queue.emit()

    def _on_watch_open_input(self) -> None:
        self.watch_open_input.emit()

    def _on_watch_open_output(self) -> None:
        self.watch_open_output.emit()

    def _on_watch_open_fail(self) -> None:
        self.watch_open_fail.emit()

    def _on_watch_apply(self) -> None:
        # Running → button is「关闭应用」: turn watch off
        if getattr(self, "_watch_apply_running", False):
            self.chk_watch_enabled.blockSignals(True)
            self.chk_watch_enabled.setChecked(False)
            self.chk_watch_enabled.blockSignals(False)
            set_watch_enabled(False)
            self.set_watch_apply_state(False)
            self._update_watch_status_label()
            self.watch_config_changed.emit()
            return

        watch = self.edit_watch_dir.text().strip()
        output = self.edit_watch_output.text().strip()
        process_existing = self.chk_watch_existing.isChecked()
        recursive = self.chk_watch_recursive.isChecked()
        archive = self.chk_watch_archive.isChecked()
        tray = self.chk_watch_tray.isChecked()

        # 「应用」= 保存并开启监视
        ok, msg = FolderWatchService.validate_dirs(
            Path(watch) if watch else None,
            Path(output) if output else None,
        )
        if not ok:
            QMessageBox.warning(self, "文件夹监视", msg)
            return
        if process_existing:
            n = 0
            try:
                root = Path(watch)
                it = root.rglob("*") if recursive else root.iterdir()
                n = sum(
                    1
                    for p in it
                    if p.is_file()
                    and p.suffix.lower()
                    in {
                        ".png",
                        ".jpg",
                        ".jpeg",
                        ".webp",
                        ".bmp",
                        ".tif",
                        ".tiff",
                        ".gif",
                    }
                )
            except OSError:
                pass
            ret = QMessageBox.question(
                self,
                "处理已有图片",
                f"开启时将尝试处理监视文件夹内约 {n} 张已有图片，是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                return

        self.chk_watch_enabled.blockSignals(True)
        self.chk_watch_enabled.setChecked(True)
        self.chk_watch_enabled.blockSignals(False)

        set_watch_dir(watch)
        set_watch_output_dir(output)
        set_watch_process_existing(process_existing)
        set_watch_recursive(recursive)
        set_watch_archive_sources(archive)
        set_watch_tray(tray)
        set_watch_enabled(True)
        self._update_watch_status_label()
        # Running state is confirmed after main window applies; optimistic update
        self.set_watch_apply_state(True)
        self.watch_config_changed.emit()

    def _build_export_page(self) -> QWidget:
        form_host = QWidget()
        form = QFormLayout(form_host)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(14)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.format_combo = QComboBox()
        self.format_combo.setMinimumWidth(160)
        for fid, label, _pf, _suf, _alpha in EXPORT_FORMATS:
            self.format_combo.addItem(label, fid)
        self.format_combo.currentIndexChanged.connect(self._on_format_combo)

        self.custom_ext_edit = QLineEdit()
        self.custom_ext_edit.setPlaceholderText("例如 heic 或 avif")
        self.custom_ext_edit.setMaxLength(8)
        self.custom_ext_edit.editingFinished.connect(self._on_custom_ext_edit)

        self.custom_ext_row = QWidget()
        custom_l = QHBoxLayout(self.custom_ext_row)
        custom_l.setContentsMargins(0, 0, 0, 0)
        custom_l.addWidget(QLabel("."))
        custom_l.addWidget(self.custom_ext_edit, 1)

        format_hint = self._hint(
            "默认导出格式。PNG/WebP/TIFF 可保留透明；JPEG/BMP 会铺白底。"
        )

        self.chk_prefix_enabled = QCheckBox("使用文件名前缀")
        self.chk_prefix_enabled.setToolTip(
            "关闭后导出/监视保存时使用原文件名（仅改扩展名）；"
            "开启后在文件名前加上右侧前缀，例如 nobg_照片.png"
        )
        self.chk_prefix_enabled.toggled.connect(self._on_prefix_enabled_toggled)

        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText("nobg_")
        self.prefix_edit.setMaxLength(32)
        self.prefix_edit.editingFinished.connect(self._on_prefix_edit)

        prefix_row = QWidget()
        prefix_l = QHBoxLayout(prefix_row)
        prefix_l.setContentsMargins(0, 0, 0, 0)
        prefix_l.setSpacing(10)
        prefix_l.addWidget(self.chk_prefix_enabled, 0)
        prefix_l.addWidget(self.prefix_edit, 1)

        form.addRow("默认导出格式", self.format_combo)
        form.addRow("自定义扩展名", self.custom_ext_row)
        form.addRow("", format_hint)
        form.addRow("文件名前缀", prefix_row)
        return self._wrap_page(form_host)

    def _build_hotkeys_page(self) -> QWidget:
        """Valorant-style rebinding: click key box → press new key."""
        block = QWidget()
        lay = QVBoxLayout(block)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        intro = self._hint(
            "点击右侧按键框，再按下想要的组合键即可改绑。"
            "若与其它功能冲突会提示并保持原设置。"
            "鼠标操作固定在下方，不可改绑。"
        )
        lay.addWidget(intro)

        # Column headers
        head = QHBoxLayout()
        head.setSpacing(12)
        head_fn = QLabel("功能")
        head_fn.setObjectName("SettingsFieldLabel")
        head_key = QLabel("按键 / 操作")
        head_key.setObjectName("SettingsFieldLabel")
        head_key.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        head_key.setMinimumWidth(132)
        head.addWidget(head_fn, 1)
        head.addWidget(head_key, 0, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(head)

        # ── Keyboard shortcuts ────────────────────────────
        kb_cap = QLabel("键盘快捷键")
        kb_cap.setObjectName("SettingsFieldLabel")
        lay.addWidget(kb_cap)

        self._hotkey_btns: dict[str, KeyCaptureButton] = {}
        for aid in HOTKEY_ORDER:
            lay.addLayout(self._make_hotkey_row(aid))

        self._hotkey_status = QLabel("")
        self._hotkey_status.setObjectName("SettingsHint")
        self._hotkey_status.setWordWrap(True)
        self._hotkey_status.setMinimumHeight(20)
        lay.addWidget(self._hotkey_status)

        # ── Reset between keyboard bindings and mouse section ──
        reset_row = QHBoxLayout()
        reset_row.setContentsMargins(0, 4, 0, 4)
        reset_row.addStretch(1)
        self.btn_reset_hotkeys = QPushButton("恢复默认")
        self.btn_reset_hotkeys.setObjectName("PrimaryBtn")
        self.btn_reset_hotkeys.setMinimumWidth(120)
        self.btn_reset_hotkeys.setMinimumHeight(36)
        self.btn_reset_hotkeys.setToolTip(
            "将全部可自定义快捷键还原为默认（鼠标操作不变）"
        )
        self.btn_reset_hotkeys.clicked.connect(self._on_reset_hotkeys)
        reset_row.addWidget(self.btn_reset_hotkeys)
        lay.addLayout(reset_row)

        # Separator only below the button (before mouse section)
        lay.addWidget(self._make_h_line())

        # ── Mouse gestures (fixed) ────────────────────────
        mouse_sections = [
            (
                "对照 / 拖出（鼠标）",
                [
                    (
                        "左键长按（单图）",
                        "显示原图；松开恢复结果（与「按住看原图」快捷键相同效果）",
                        "鼠标 · 左键长按",
                    ),
                    (
                        "左键长按（并排）",
                        "并排时在一侧长按，该侧原位换成另一张；松开恢复",
                        "鼠标 · 左键长按",
                    ),
                    (
                        "左键拖移",
                        "拖出结果文件到文件夹或其他软件（优先于长按看原图）",
                        "鼠标 · 左键拖移",
                    ),
                ],
            ),
            (
                "多图 / 预览（鼠标）",
                [
                    ("点击缩略图", "进入单张预览", "鼠标 · 单击"),
                    ("右键（预览）", "返回网格", "鼠标 · 右键"),
                    ("右键（网格/单图）", "用已下载模型重抠", "鼠标 · 右键"),
                ],
            ),
        ]
        for section, items in mouse_sections:
            cap = QLabel(section)
            cap.setObjectName("SettingsFieldLabel")
            lay.addWidget(cap)
            for title, desc, gesture in items:
                lay.addLayout(self._make_gesture_row(title, desc, gesture))

        return self._wrap_page(block)

    def _make_h_line(self) -> QFrame:
        line = QFrame()
        line.setObjectName("HotkeySeparator")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setFixedHeight(1)
        line.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        return line

    def _make_hotkey_row(self, aid: str) -> QHBoxLayout:
        """Left: title + description · Right: rebindable key capture."""
        row = QHBoxLayout()
        row.setSpacing(12)
        row.setContentsMargins(0, 4, 0, 4)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.setContentsMargins(0, 0, 0, 0)
        title = QLabel(action_label(aid))
        title.setObjectName("HotkeyActionTitle")
        title.setMinimumWidth(72)
        title.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        title_col.addWidget(title)
        desc = (action_description(aid) or "").strip()
        if desc:
            hint = QLabel(desc)
            hint.setObjectName("SettingsHint")
            hint.setWordWrap(True)
            title_col.addWidget(hint)

        btn = KeyCaptureButton()
        btn.setFixedWidth(132)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn.set_sequence(get_hotkey(aid))
        btn.setToolTip(f"{action_label(aid)}：点击后按下新快捷键")
        btn.capture_started.connect(
            lambda b=btn: self._on_hotkey_capture_started(b)
        )
        btn.captured.connect(lambda seq, a=aid: self._on_hotkey_captured(a, seq))
        btn.capture_cancelled.connect(self._on_hotkey_capture_cancelled)
        self._hotkey_btns[aid] = btn

        row.addLayout(title_col, 1)
        row.addWidget(
            btn, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        return row

    def _make_gesture_row(self, title: str, desc: str, gesture: str) -> QHBoxLayout:
        """Same layout as hotkey rows; right side is a fixed mouse-gesture badge."""
        row = QHBoxLayout()
        row.setSpacing(12)
        row.setContentsMargins(0, 4, 0, 4)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.setContentsMargins(0, 0, 0, 0)
        t = QLabel(title)
        t.setObjectName("HotkeyActionTitle")
        t.setMinimumWidth(72)
        t.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        title_col.addWidget(t)
        if desc:
            hint = QLabel(desc)
            hint.setObjectName("SettingsHint")
            hint.setWordWrap(True)
            title_col.addWidget(hint)

        badge = QLabel(gesture)
        badge.setObjectName("HotkeyGestureBadge")
        badge.setFixedWidth(132)
        badge.setMinimumHeight(32)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setToolTip("鼠标操作，不可改绑为键盘")
        badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        row.addLayout(title_col, 1)
        row.addWidget(
            badge, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        return row

    def _stop_all_hotkey_captures(self, *, except_btn: object = None) -> None:
        for btn in getattr(self, "_hotkey_btns", {}).values():
            if btn is except_btn:
                continue
            if btn.is_recording():
                btn.stop_capture(emit_cancel=False)

    def _on_hotkey_capture_started(self, active_btn: KeyCaptureButton) -> None:
        """Only one key box can record at a time."""
        self._stop_all_hotkey_captures(except_btn=active_btn)
        if hasattr(self, "_hotkey_status"):
            self._hotkey_status.setText("请按下新的快捷键…（再点一次该框可取消）")

    def _on_hotkey_capture_cancelled(self) -> None:
        if hasattr(self, "_hotkey_status"):
            self._hotkey_status.setText("已取消改绑。")

    def _refresh_hotkey_buttons(self) -> None:
        btns = getattr(self, "_hotkey_btns", None)
        if not btns:
            return
        for aid, btn in btns.items():
            if btn.is_recording():
                btn.stop_capture(emit_cancel=False)
            btn.set_sequence(get_hotkey(aid))

    def _on_hotkey_captured(self, action_id: str, sequence: str) -> None:
        ok, msg = set_hotkey(action_id, sequence)
        btn = self._hotkey_btns.get(action_id)
        if btn is not None:
            # Always show stored value (revert UI on conflict / invalid)
            btn.set_sequence(get_hotkey(action_id))
        if hasattr(self, "_hotkey_status"):
            self._hotkey_status.setText(msg)
        if ok:
            self.hotkeys_changed.emit()

    def _on_reset_hotkeys(self) -> None:
        # Finish any in-progress capture first
        self._stop_all_hotkey_captures()
        ret = QMessageBox.question(
            self,
            "恢复默认快捷键",
            "确定将全部可自定义快捷键恢复为默认？\n鼠标操作不会改变。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            if hasattr(self, "_hotkey_status"):
                self._hotkey_status.setText("已取消恢复默认。")
            return
        reset_hotkeys()
        self._refresh_hotkey_buttons()
        if hasattr(self, "_hotkey_status"):
            self._hotkey_status.setText("已将全部快捷键恢复为默认。")
        self.hotkeys_changed.emit()

    def _update_custom_ext_visible(self) -> None:
        is_custom = self.format_combo.currentData() == "custom"
        self.custom_ext_row.setVisible(bool(is_custom))

    def _invalidate_model_disk_cache(self) -> None:
        self._model_disk_cache = None

    def _model_disk_snapshot(self, *, force: bool = False) -> dict[str, tuple[str, int]]:
        """Cached one-shot directory scan for model file status."""
        if force or self._model_disk_cache is None:
            self._model_disk_cache = catalog_disk_snapshot()
        return self._model_disk_cache

    def _model_status_of(self, model_id: str) -> str:
        st, _sz = self._model_disk_snapshot().get(model_id, ("missing", 0))
        return st

    def _model_size_of(self, model_id: str) -> int:
        _st, sz = self._model_disk_snapshot().get(model_id, ("missing", 0))
        return int(sz)

    def _set_label_text(self, label: QLabel, text: str) -> None:
        if label.text() != text:
            label.setText(text)

    def _set_button_text(self, btn: QPushButton, text: str) -> None:
        if btn.text() != text:
            btn.setText(text)

    def _set_body_text(self, box: QTextEdit, text: str) -> None:
        if box.toPlainText() != text:
            box.setPlainText(text)

    def _refresh_model_combo_labels(self, *, force_disk: bool = True) -> None:
        """Update 已下载/未下载 marks without changing selection data ids."""
        if not hasattr(self, "model_combo"):
            return
        snap = self._model_disk_snapshot(force=force_disk)
        cur = self.model_combo.currentData()
        self.model_combo.blockSignals(True)
        for i in range(self.model_combo.count()):
            mid = self.model_combo.itemData(i)
            info = get_model_info(str(mid)) if mid else None
            if info is None:
                continue
            st, _sz = snap.get(info.id, ("missing", 0))
            new_text = model_combo_label(info, status=st)
            if self.model_combo.itemText(i) != new_text:
                self.model_combo.setItemText(i, new_text)
        # Keep selection; avoid setCurrentIndex if already correct (reduces churn)
        if cur is not None:
            idx = self.model_combo.findData(cur)
            if idx >= 0 and self.model_combo.currentIndex() != idx:
                self.model_combo.setCurrentIndex(idx)
        self.model_combo.blockSignals(False)

    def _selected_model_id(self) -> str:
        data = self.model_combo.currentData() if hasattr(self, "model_combo") else None
        return str(data) if data else ""

    def _refresh_model_help(self, *, force_disk: bool = False) -> None:
        mid = self._selected_model_id()
        info = get_model_info(mid) if mid else None
        # Cache applied model string for preview path (avoid QSettings every keystroke)
        if force_disk or not self._cached_applied_model:
            self._cached_applied_model = get_model()
        applied = self._cached_applied_model
        applied_info = get_model_info(applied)
        applied_label = applied_info.label if applied_info else applied
        snap = self._model_disk_snapshot(force=force_disk)

        if info:
            self._set_body_text(self.model_skill, info.skill)
            self._set_body_text(self.model_note, info.note or "—")
            st, size = snap.get(info.id, ("missing", 0))
            if st == "downloaded":
                mb = size / 1e6 if size else 0
                local = f"本地已下载（约 {mb:.0f} MB）" if mb >= 1 else "本地已下载"
            elif st == "partial":
                mb = size / 1e6
                local = f"未下完（已缓存约 {mb:.1f} MB，可续传）"
            else:
                local = "未下载（需联网，点「下载并应用」并确认）"
            is_current = info.id == applied
            cur = "当前默认 ✓" if is_current else f"当前默认：{applied_label}"
            status = f"选中：{info.label} — {local}\n{cur}"
            if hasattr(self, "model_status"):
                self._set_label_text(self.model_status, status)
        else:
            self._set_body_text(self.model_skill, "—")
            self._set_body_text(self.model_note, "—")
            if hasattr(self, "model_status"):
                self._set_label_text(self.model_status, f"当前默认：{applied_label}")
        if hasattr(self, "btn_clear_partial"):
            any_partial = any(st == "partial" for st, _sz in snap.values())
            self.btn_clear_partial.setEnabled(any_partial)
        self._update_model_action_buttons()

    def _update_model_action_buttons(self) -> None:
        if not hasattr(self, "btn_apply_model"):
            return
        mid = self._selected_model_id()
        if not mid:
            self.btn_apply_model.setEnabled(False)
            self.btn_uninstall_model.setEnabled(False)
            return
        st = self._model_status_of(mid)
        applied = self._cached_applied_model or get_model()
        if st == "downloaded":
            if mid == applied:
                self._set_button_text(self.btn_apply_model, "已是当前默认")
                self.btn_apply_model.setEnabled(False)
            else:
                self._set_button_text(self.btn_apply_model, "应用为默认")
                self.btn_apply_model.setEnabled(True)
            self.btn_uninstall_model.setEnabled(True)
        elif st == "partial":
            self._set_button_text(self.btn_apply_model, "继续下载…")
            self.btn_apply_model.setEnabled(True)
            self.btn_uninstall_model.setEnabled(True)
        else:
            self._set_button_text(self.btn_apply_model, "下载并应用…")
            self.btn_apply_model.setEnabled(True)
            self.btn_uninstall_model.setEnabled(False)

    def _on_clear_partial_downloads(self) -> None:
        n = delete_incomplete_downloads()
        self._invalidate_model_disk_cache()
        self._refresh_model_combo_labels(force_disk=True)
        self._refresh_model_help(force_disk=True)
        if n:
            self.model_dl_hint.setText(
                f"已删除 {n} 个未完成文件。对应模型下次将从头下载。"
            )
        else:
            self.model_dl_hint.setText("没有未完成的下载文件。")

    def _on_theme_combo(self, _index: int) -> None:
        data = self.theme_combo.currentData()
        if not data:
            return
        theme = str(data)
        set_theme(theme)
        self.theme_changed.emit(theme)

    def _on_model_combo_preview(self, _index: int) -> None:
        """Browse only: update skill/note/buttons — no settings write, no download."""
        # Use cached disk snapshot; do not re-scan models/ on every dropdown move
        self._refresh_model_help(force_disk=False)

    def _on_apply_or_download_model(self) -> None:
        mid = self._selected_model_id()
        if not mid or not get_model_info(mid):
            return
        info = get_model_info(mid)
        assert info is not None
        # Fresh scan before download/apply decision
        self._invalidate_model_disk_cache()
        st = self._model_status_of(mid)

        if st != "downloaded":
            if st == "partial":
                mb = self._model_size_of(mid) / 1e6
                body = (
                    f"将继续下载「{info.label}」（{info.id}）。\n"
                    f"本地已有约 {mb:.1f} MB 未完成文件，将续传。\n\n"
                    "下载过程中请保持联网；可随时在设置中换回已下载模型以取消。"
                )
            else:
                body = (
                    f"将下载「{info.label}」（{info.id}）并设为默认模型。\n"
                    f"{info.note or ''}\n\n"
                    "文件会保存到程序 models 目录；体积可能较大，需联网。"
                    "确认后才会开始下载。"
                )
            reply = QMessageBox.question(
                self,
                "确认下载模型",
                body.strip(),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        set_model(mid)
        self._cached_applied_model = mid
        self._refresh_model_combo_labels(force_disk=True)
        self._refresh_model_help(force_disk=False)
        if st == "downloaded":
            self.model_dl_hint.setText(f"已将默认模型设为「{info.label}」。")
        else:
            self.model_dl_hint.setText(
                f"已确认：开始下载并应用「{info.label}」…"
            )
        self.model_changed.emit(mid)

    def _on_uninstall_model(self) -> None:
        mid = self._selected_model_id()
        if not mid:
            return
        info = get_model_info(mid)
        label = info.label if info else mid
        self._invalidate_model_disk_cache()
        st = self._model_status_of(mid)
        if st == "missing":
            QMessageBox.information(self, "卸载模型", "本地没有该模型文件。")
            return

        size = self._model_size_of(mid)
        size_hint = f"（约 {size / 1e6:.0f} MB）" if size > 1024 else ""
        was_applied = (self._cached_applied_model or get_model()) == mid
        extra = ""
        if was_applied:
            fallback = pick_fallback_model_id(exclude=mid)
            fb_info = get_model_info(fallback)
            fb_label = fb_info.label if fb_info else fallback
            extra = f"\n\n该模型是当前默认，卸载后将改用「{fb_label}」。"
        if mid == product_default_model_id():
            extra += (
                "\n\n提示：若为安装包内置默认模型，下次启动可能会重新释放一份副本。"
            )

        reply = QMessageBox.question(
            self,
            "确认卸载模型",
            f"确定删除「{label}」的本地文件 {size_hint}？\n"
            f"将移除 models 下的 {mid}.onnx（及未完成 .part）。"
            f"{extra}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        ok, msg = delete_model_files(mid)
        if not ok:
            QMessageBox.warning(self, "卸载失败", msg)
            return

        switched = ""
        if was_applied:
            fallback = pick_fallback_model_id(exclude=mid)
            set_model(fallback)
            self._cached_applied_model = fallback
            self.model_changed.emit(fallback)
            fb_info = get_model_info(fallback)
            switched = f" 默认已改为「{fb_info.label if fb_info else fallback}」。"

        self._invalidate_model_disk_cache()
        self._refresh_model_combo_labels(force_disk=True)
        # 下拉保持在当前选中项，便于继续浏览
        idx = self.model_combo.findData(mid)
        if idx >= 0:
            self.model_combo.blockSignals(True)
            if self.model_combo.currentIndex() != idx:
                self.model_combo.setCurrentIndex(idx)
            self.model_combo.blockSignals(False)
        self._refresh_model_help(force_disk=False)
        self.model_dl_hint.setText(f"{msg}。{switched}".strip())

    def _on_alpha_toggle(self, checked: bool) -> None:
        set_alpha_matting(checked)
        self.alpha_matting_changed.emit(checked)

    def _refresh_accel_ui(self) -> None:
        """Update checkbox + status. Status only shown when「更快处理」is on."""
        if not hasattr(self, "chk_prefer_accel"):
            return
        if self._accel_status_cache is None:
            self._accel_status_cache = detect_accel()
        status = self._accel_status_cache
        prefer = get_prefer_accel()
        self.chk_prefer_accel.blockSignals(True)
        self.chk_prefer_accel.setChecked(prefer)
        self.chk_prefer_accel.setEnabled(True)
        self.chk_prefer_accel.blockSignals(False)

        if not hasattr(self, "accel_status"):
            return

        # Closed: no extra status text under the checkbox
        if not prefer:
            self.accel_status.clear()
            self.accel_status.setToolTip("")
            self.accel_status.setVisible(False)
            return

        # Prefer actual engine mode after load when available
        device = ""
        win = self.window()
        eng = getattr(win, "engine", None) if win is not None else None
        if eng is not None:
            device = (getattr(eng, "device_label", None) or "").strip()
        note = (getattr(eng, "last_accel_note", None) or "").strip() if eng else ""

        if status.available:
            # Machine has accel components; still may run as 普通 if load fell back
            if device and "普通" in device:
                line = (
                    "已开启更快处理，但当前为普通模式"
                    "（加速未生效或已自动回退，不影响使用）。"
                )
            elif device:
                line = f"已开启更快处理，当前为加速模式（{device}）。"
            else:
                line = (
                    f"已开启更快处理，本机支持加速（{status.summary}）；"
                    "加载模型后将尽量使用加速，失败会自动回普通模式。"
                )
        else:
            line = (
                "已开启更快处理，但当前电脑未检测到加速组件，"
                "目前仍为普通模式，不影响正常使用。"
            )
        if note and "加速不可用" in note:
            line = (
                "已开启更快处理，加速加载失败，已自动改用普通模式"
                "（不影响使用）。"
            )

        self.accel_status.setText(line)
        self.accel_status.setToolTip(status.detail or line)
        self.accel_status.setVisible(True)

    def _on_prefer_accel_toggle(self, checked: bool) -> None:
        set_prefer_accel(checked)
        self._refresh_accel_ui()
        self.prefer_accel_changed.emit(bool(checked))

    def _on_format_combo(self, _index: int) -> None:
        data = self.format_combo.currentData()
        if not data:
            return
        set_export_format(str(data))
        self._update_custom_ext_visible()
        self.export_format_changed.emit(str(data))

    def _on_custom_ext_edit(self) -> None:
        set_export_custom_ext(self.custom_ext_edit.text())
        self.custom_ext_edit.blockSignals(True)
        self.custom_ext_edit.setText(get_export_custom_ext())
        self.custom_ext_edit.blockSignals(False)
        self.export_format_changed.emit(get_export_format())

    def _sync_prefix_enabled_ui(self) -> None:
        on = self.chk_prefix_enabled.isChecked()
        self.prefix_edit.setEnabled(on)
        self.prefix_edit.setPlaceholderText("nobg_" if on else "（已关闭前缀）")

    def _on_prefix_enabled_toggled(self, checked: bool) -> None:
        set_export_prefix_enabled(bool(checked))
        self._sync_prefix_enabled_ui()
        self.export_prefix_changed.emit(get_effective_export_prefix())

    def _on_prefix_edit(self) -> None:
        set_export_prefix(self.prefix_edit.text())
        self.prefix_edit.blockSignals(True)
        self.prefix_edit.setText(get_export_prefix())
        self.prefix_edit.blockSignals(False)
        self.export_prefix_changed.emit(get_effective_export_prefix())


SettingsDialog = SettingsPage
