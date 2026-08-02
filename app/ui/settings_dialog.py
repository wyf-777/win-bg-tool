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

from app.engines.local_rembg import delete_incomplete_downloads, partial_download_bytes
from app.engines.models_catalog import (
    MODEL_CATALOG,
    get_model_info,
    is_model_partial,
    model_combo_label,
    model_download_status,
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
    export_prefix_changed = Signal(str)
    alpha_matting_changed = Signal(bool)
    prefer_accel_changed = Signal(bool)  # F14 soft GPU preference
    watch_config_changed = Signal()  # F13 apply/start/stop from settings
    watch_pause_toggled = Signal()  # pause / resume
    watch_clear_queue = Signal()
    watch_open_output = Signal()
    watch_open_fail = Signal()
    watch_retry_failed = Signal()
    hotkeys_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsPage")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

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

        self._refresh_model_combo_labels()
        midx = max(0, self.model_combo.findData(get_model()))
        self.model_combo.blockSignals(True)
        self.model_combo.setCurrentIndex(midx)
        self.model_combo.blockSignals(False)
        self._refresh_model_help()

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
            "已下载=可立即用；未下完=下次自动续传；未下载=需联网获取"
        )
        for info in MODEL_CATALOG:
            self.model_combo.addItem(model_combo_label(info), info.id)
        self.model_combo.currentIndexChanged.connect(self._on_model_combo)
        row.addWidget(lab, 0)
        row.addWidget(self.model_combo, 1)
        lay.addLayout(row)

        self.model_dl_hint = self._hint(
            "已下载 / 未下完 / 未下载。"
            "中途退出或换模型会保留进度，下次继续下载；也可点下方清理未完成文件。"
        )
        lay.addWidget(self.model_dl_hint)

        clean_row = QHBoxLayout()
        clean_row.addStretch(1)
        self.btn_clear_partial = QPushButton("清理未完成下载")
        self.btn_clear_partial.setObjectName("ActionBtn")
        self.btn_clear_partial.setToolTip(
            "删除 models 目录里所有 .part 半成品，下次将从头下载"
        )
        self.btn_clear_partial.clicked.connect(self._on_clear_partial_downloads)
        clean_row.addWidget(self.btn_clear_partial)
        lay.addLayout(clean_row)

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
        self.model_status.setMinimumHeight(20)
        self.model_status.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        lay.addWidget(self.model_status)

        self.chk_alpha = QCheckBox("启用 Alpha Matting（边缘更细，更慢）")
        self.chk_alpha.toggled.connect(self._on_alpha_toggle)
        lay.addWidget(self.chk_alpha)

        # F14 — plain language; never block users without GPU
        accel_cap = QLabel("处理速度")
        accel_cap.setObjectName("SettingsFieldLabel")
        lay.addWidget(accel_cap)

        self.chk_prefer_accel = QCheckBox("更快处理（有条件时用显卡加速）")
        self.chk_prefer_accel.setToolTip(
            "默认使用普通模式，人人可用。"
            "勾选后，若本机支持会尽量加速；不支持或失败会自动改回普通模式。"
        )
        self.chk_prefer_accel.toggled.connect(self._on_prefer_accel_toggle)
        lay.addWidget(self.chk_prefer_accel)

        self.accel_status = QLabel("")
        self.accel_status.setObjectName("SettingsHint")
        self.accel_status.setWordWrap(True)
        self.accel_status.setMinimumHeight(36)
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

    def _build_watch_page(self) -> QWidget:
        """F13 hot folder — defaults match design-folder-watch."""
        block = QWidget()
        lay = QVBoxLayout(block)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        intro = self._hint(
            "把图片放进「监视文件夹」，会自动抠图并保存到输出文件夹。"
            "默认不占用主界面列表；默认只处理开启监视之后的新文件。"
        )
        lay.addWidget(intro)

        self.chk_watch_enabled = QCheckBox("开启文件夹监视")
        self.chk_watch_enabled.setToolTip("开启后后台监视进图目录，自动抠图并导出")
        lay.addWidget(self.chk_watch_enabled)

        # watch dir
        row_w = QHBoxLayout()
        self.edit_watch_dir = QLineEdit()
        self.edit_watch_dir.setPlaceholderText("选择要监视的文件夹…")
        self.edit_watch_dir.setReadOnly(True)
        btn_w = QPushButton("浏览…")
        btn_w.setObjectName("ActionBtn")
        btn_w.clicked.connect(self._browse_watch_dir)
        row_w.addWidget(self.edit_watch_dir, 1)
        row_w.addWidget(btn_w)
        lay.addWidget(QLabel("监视文件夹（进图）"))
        lay.addLayout(row_w)

        # output dir
        row_o = QHBoxLayout()
        self.edit_watch_output = QLineEdit()
        self.edit_watch_output.setPlaceholderText(
            f"默认：监视文件夹下的「{DEFAULT_OUTPUT_SUBDIR}」"
        )
        self.edit_watch_output.setReadOnly(True)
        btn_o = QPushButton("浏览…")
        btn_o.setObjectName("ActionBtn")
        btn_o.clicked.connect(self._browse_watch_output)
        btn_o_clear = QPushButton("用默认")
        btn_o_clear.setObjectName("ActionBtn")
        btn_o_clear.setToolTip(f"恢复为 监视目录/{DEFAULT_OUTPUT_SUBDIR}")
        btn_o_clear.clicked.connect(self._clear_watch_output)
        row_o.addWidget(self.edit_watch_output, 1)
        row_o.addWidget(btn_o)
        row_o.addWidget(btn_o_clear)
        lay.addWidget(QLabel("输出文件夹（结果）"))
        lay.addLayout(row_o)

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
        lay.addWidget(self.chk_watch_existing)

        self.chk_watch_recursive = QCheckBox("包含子文件夹")
        self.chk_watch_recursive.setToolTip(
            "开启后会扫描子目录中的图片；结果按相对路径写入输出文件夹"
        )
        lay.addWidget(self.chk_watch_recursive)

        self.chk_watch_archive = QCheckBox(
            f"成功后把原图移到「{DEFAULT_ARCHIVE_SUBDIR}」"
        )
        self.chk_watch_archive.setToolTip(
            "抠图成功后把源文件移到监视目录下的「已处理」，避免进图夹越堆越多"
        )
        lay.addWidget(self.chk_watch_archive)

        self.chk_watch_tray = QCheckBox("监视开启时，关闭窗口最小化到托盘")
        self.chk_watch_tray.setToolTip(
            "方便后台继续监视；在托盘图标上可重新打开窗口或退出"
        )
        lay.addWidget(self.chk_watch_tray)

        self.watch_hint = self._hint(
            f"输出默认在「{DEFAULT_OUTPUT_SUBDIR}」；失败在「失败」。"
            "清单保存在应用数据中，不会出现在导出文件夹。"
            "导出格式与前缀跟「导出」一致。"
        )
        lay.addWidget(self.watch_hint)

        self.watch_status = QLabel("")
        self.watch_status.setObjectName("SettingsHint")
        self.watch_status.setWordWrap(True)
        lay.addWidget(self.watch_status)

        # Runtime controls (work when watch is running)
        run_row = QHBoxLayout()
        self.btn_watch_pause = QPushButton("暂停")
        self.btn_watch_pause.setObjectName("ActionBtn")
        self.btn_watch_pause.setToolTip("暂停接收与处理（正在抠的一张会跑完）")
        self.btn_watch_pause.clicked.connect(self._on_watch_pause_clicked)
        self.btn_watch_clear = QPushButton("清空队列")
        self.btn_watch_clear.setObjectName("ActionBtn")
        self.btn_watch_clear.setToolTip("清空等待中的文件（不中断当前这一张）")
        self.btn_watch_clear.clicked.connect(self._on_watch_clear_clicked)
        self.btn_watch_retry = QPushButton("重试失败")
        self.btn_watch_retry.setObjectName("ActionBtn")
        self.btn_watch_retry.setToolTip("把最近失败且源文件仍在的项目重新排队")
        self.btn_watch_retry.clicked.connect(lambda: self.watch_retry_failed.emit())
        self.btn_watch_open_out = QPushButton("打开输出")
        self.btn_watch_open_out.setObjectName("ActionBtn")
        self.btn_watch_open_out.clicked.connect(self._on_watch_open_output)
        self.btn_watch_open_fail = QPushButton("打开失败")
        self.btn_watch_open_fail.setObjectName("ActionBtn")
        self.btn_watch_open_fail.setToolTip("打开失败目录（错误说明 + 源文件副本）")
        self.btn_watch_open_fail.clicked.connect(self._on_watch_open_fail)
        run_row.addWidget(self.btn_watch_pause)
        run_row.addWidget(self.btn_watch_clear)
        run_row.addWidget(self.btn_watch_retry)
        run_row.addWidget(self.btn_watch_open_out)
        run_row.addWidget(self.btn_watch_open_fail)
        run_row.addStretch(1)
        lay.addLayout(run_row)

        apply_row = QHBoxLayout()
        apply_row.addStretch(1)
        self.btn_watch_apply = QPushButton("应用")
        self.btn_watch_apply.setObjectName("PrimaryBtn")
        self.btn_watch_apply.setToolTip("保存设置并开启/关闭监视")
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
        self.edit_watch_dir.setText(get_watch_dir())
        out = get_watch_output_dir()
        self.edit_watch_output.setText(out)
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

    def set_watch_runtime_status(self, text: str) -> None:
        if hasattr(self, "watch_status"):
            self.watch_status.setText(text or "")

    def set_watch_pause_label(self, paused: bool) -> None:
        if hasattr(self, "btn_watch_pause"):
            self.btn_watch_pause.setText("继续" if paused else "暂停")

    def _update_watch_status_label(self) -> None:
        if not hasattr(self, "watch_status"):
            return
        w = get_watch_dir()
        if get_watch_enabled() and w:
            out = get_watch_output_dir() or f"{w}\\{DEFAULT_OUTPUT_SUBDIR}"
            self.watch_status.setText(f"已保存：监视开启 · {w} → {out}")
        elif w:
            self.watch_status.setText("已保存路径；监视当前为关闭（勾选后点应用）")
        else:
            self.watch_status.setText("选择监视文件夹后，勾选开启并点「应用」。")

    def _browse_watch_dir(self) -> None:
        start = get_watch_dir() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "选择监视文件夹", start)
        if path:
            self.edit_watch_dir.setText(path)

    def _browse_watch_output(self) -> None:
        start = get_watch_output_dir() or get_watch_dir() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "选择输出文件夹", start)
        if path:
            self.edit_watch_output.setText(path)

    def _clear_watch_output(self) -> None:
        self.edit_watch_output.clear()

    def _on_watch_pause_clicked(self) -> None:
        self.watch_pause_toggled.emit()

    def _on_watch_clear_clicked(self) -> None:
        self.watch_clear_queue.emit()

    def _on_watch_open_output(self) -> None:
        self.watch_open_output.emit()

    def _on_watch_open_fail(self) -> None:
        self.watch_open_fail.emit()

    def _on_watch_apply(self) -> None:
        watch = self.edit_watch_dir.text().strip()
        output = self.edit_watch_output.text().strip()
        enabled = self.chk_watch_enabled.isChecked()
        process_existing = self.chk_watch_existing.isChecked()
        recursive = self.chk_watch_recursive.isChecked()
        archive = self.chk_watch_archive.isChecked()
        tray = self.chk_watch_tray.isChecked()

        if enabled:
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

        set_watch_dir(watch)
        set_watch_output_dir(output)
        set_watch_process_existing(process_existing)
        set_watch_recursive(recursive)
        set_watch_archive_sources(archive)
        set_watch_tray(tray)
        set_watch_enabled(enabled)
        self._update_watch_status_label()
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

        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText("nobg_")
        self.prefix_edit.setMaxLength(32)
        self.prefix_edit.editingFinished.connect(self._on_prefix_edit)
        prefix_hint = self._hint("可选：文件名前缀，例如 nobg_照片.png")

        form.addRow("默认导出格式", self.format_combo)
        form.addRow("自定义扩展名", self.custom_ext_row)
        form.addRow("", format_hint)
        form.addRow("文件名前缀", self.prefix_edit)
        form.addRow("", prefix_hint)
        return self._wrap_page(form_host)

    def _build_hotkeys_page(self) -> QWidget:
        """Valorant-style rebinding: click key box → press new key."""
        block = QWidget()
        lay = QVBoxLayout(block)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        # Column headers: 功能 | 按键（可自定义）
        head = QHBoxLayout()
        head.setSpacing(12)
        head_fn = QLabel("功能")
        head_fn.setObjectName("SettingsFieldLabel")
        head_key = QLabel("按键（可自定义）")
        head_key.setObjectName("SettingsFieldLabel")
        head_key.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        head_key.setMinimumWidth(132)
        head.addWidget(head_fn, 1)
        head.addWidget(head_key, 0, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(head)

        self._hotkey_btns: dict[str, KeyCaptureButton] = {}
        for aid in HOTKEY_ORDER:
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
            btn.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
            )
            btn.set_sequence(get_hotkey(aid))
            btn.setToolTip(f"{action_label(aid)}：点击后按下新快捷键")
            btn.captured.connect(
                lambda seq, a=aid: self._on_hotkey_captured(a, seq)
            )
            self._hotkey_btns[aid] = btn

            row.addLayout(title_col, 1)
            row.addWidget(
                btn, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            lay.addLayout(row)

        self._hotkey_status = QLabel("")
        self._hotkey_status.setObjectName("SettingsHint")
        self._hotkey_status.setWordWrap(True)
        lay.addWidget(self._hotkey_status)

        reset_row = QHBoxLayout()
        reset_row.addStretch(1)
        self.btn_reset_hotkeys = QPushButton("恢复默认")
        self.btn_reset_hotkeys.setObjectName("ActionBtn")
        self.btn_reset_hotkeys.setToolTip("将全部快捷键还原为默认")
        self.btn_reset_hotkeys.clicked.connect(self._on_reset_hotkeys)
        reset_row.addWidget(self.btn_reset_hotkeys)
        lay.addLayout(reset_row)

        # Mouse-only actions (not keyboard rebindable)
        mouse_ops = [
            ("对照 / 拖出（鼠标）", [
                ("左键长按（单图）", "显示原图；松开恢复结果"),
                ("左键长按（并排）", "该侧原位换成另一张；松开恢复"),
                ("「左右对照」按钮", "左原图 / 右结果并排"),
                ("左键拖移", "拖出结果文件（优先于长按）"),
            ]),
            ("多图 / 灯箱（鼠标）", [
                ("点击缩略图", "进入单张预览（灯箱）"),
                ("右键（灯箱）", "返回网格"),
                ("右键（网格/单图）", "用已下载模型重抠"),
            ]),
        ]
        for section, items in mouse_ops:
            cap = QLabel(section)
            cap.setObjectName("SettingsFieldLabel")
            lay.addWidget(cap)
            body = QLabel(
                "\n".join(f"  {key}  —  {desc}" for key, desc in items)
            )
            body.setObjectName("SettingsBodyText")
            body.setWordWrap(True)
            body.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
            body.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            lay.addWidget(body)

        return self._wrap_page(block)

    def _refresh_hotkey_buttons(self) -> None:
        btns = getattr(self, "_hotkey_btns", None)
        if not btns:
            return
        for aid, btn in btns.items():
            if not btn.is_recording():
                btn.set_sequence(get_hotkey(aid))

    def _on_hotkey_captured(self, action_id: str, sequence: str) -> None:
        ok, msg = set_hotkey(action_id, sequence)
        btn = self._hotkey_btns.get(action_id)
        if btn is not None:
            # Always show stored value (revert on conflict)
            btn.set_sequence(get_hotkey(action_id))
        if hasattr(self, "_hotkey_status"):
            self._hotkey_status.setText(msg)
        if ok:
            self.hotkeys_changed.emit()

    def _on_reset_hotkeys(self) -> None:
        reset_hotkeys()
        self._refresh_hotkey_buttons()
        if hasattr(self, "_hotkey_status"):
            self._hotkey_status.setText("已恢复默认快捷键。")
        self.hotkeys_changed.emit()

    def _update_custom_ext_visible(self) -> None:
        is_custom = self.format_combo.currentData() == "custom"
        self.custom_ext_row.setVisible(bool(is_custom))

    def _refresh_model_combo_labels(self) -> None:
        """Update 已下载/未下载 marks without changing selection data ids."""
        if not hasattr(self, "model_combo"):
            return
        cur = self.model_combo.currentData()
        self.model_combo.blockSignals(True)
        for i in range(self.model_combo.count()):
            mid = self.model_combo.itemData(i)
            info = get_model_info(str(mid)) if mid else None
            if info is None:
                continue
            self.model_combo.setItemText(i, model_combo_label(info))
        if cur is not None:
            idx = self.model_combo.findData(cur)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
        self.model_combo.blockSignals(False)

    def _refresh_model_help(self) -> None:
        mid = self.model_combo.currentData()
        info = get_model_info(str(mid)) if mid else None
        if info:
            self.model_skill.setPlainText(info.skill)
            self.model_note.setPlainText(info.note or "—")
            st = model_download_status(info.id)
            if st == "downloaded":
                status = "状态：已下载（本地可用）"
            elif st == "partial":
                mb = partial_download_bytes(info.id) / 1e6
                status = f"状态：未下完（已缓存约 {mb:.1f} MB，下次/再选会续传）"
            else:
                status = "状态：未下载（首次使用需联网）"
            if hasattr(self, "model_status"):
                self.model_status.setText(status)
        else:
            self.model_skill.setPlainText("—")
            self.model_note.setPlainText("—")
            if hasattr(self, "model_status"):
                self.model_status.setText("")
        # Enable clean button only when something incomplete exists
        if hasattr(self, "btn_clear_partial"):
            any_partial = any(is_model_partial(m.id) for m in MODEL_CATALOG)
            self.btn_clear_partial.setEnabled(any_partial)

    def _on_clear_partial_downloads(self) -> None:
        n = delete_incomplete_downloads()
        self._refresh_model_combo_labels()
        self._refresh_model_help()
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

    def _on_model_combo(self, _index: int) -> None:
        data = self.model_combo.currentData()
        if not data:
            return
        model_id = str(data)
        set_model(model_id)
        # 只更新文案；不要在切换时重写整表「已下载」前缀（会触发布局抖动）
        self._refresh_model_help()
        self.model_changed.emit(model_id)

    def _on_alpha_toggle(self, checked: bool) -> None:
        set_alpha_matting(checked)
        self.alpha_matting_changed.emit(checked)

    def _refresh_accel_ui(self) -> None:
        """Probe machine capability; keep checkbox usable for all users."""
        if not hasattr(self, "chk_prefer_accel"):
            return
        status = detect_accel()
        prefer = get_prefer_accel()
        self.chk_prefer_accel.blockSignals(True)
        self.chk_prefer_accel.setChecked(prefer)
        # Always leave checkbox enabled: preference is "when possible"
        self.chk_prefer_accel.setEnabled(True)
        self.chk_prefer_accel.blockSignals(False)

        if status.available:
            if prefer:
                line = f"状态：{status.summary} · 已开启更快处理（失败会自动退回普通模式）"
            else:
                line = f"状态：{status.summary} · 当前使用普通模式（可勾选上方以尝试加速）"
        else:
            if prefer:
                line = (
                    "状态：普通模式 · 已记住「更快处理」，"
                    "但当前电脑未检测到加速组件，将继续用普通模式。"
                )
            else:
                line = "状态：普通模式 · 人人可用（未检测到加速组件）"
        if hasattr(self, "accel_status"):
            self.accel_status.setText(line)
            self.accel_status.setToolTip(status.detail)

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

    def _on_prefix_edit(self) -> None:
        set_export_prefix(self.prefix_edit.text())
        self.prefix_edit.blockSignals(True)
        self.prefix_edit.setText(get_export_prefix())
        self.prefix_edit.blockSignals(False)
        self.export_prefix_changed.emit(get_export_prefix())


SettingsDialog = SettingsPage
