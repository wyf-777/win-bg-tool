"""Edge-style full-window settings: left nav + right detail."""

from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
from app.services.export import EXPORT_FORMATS
from app.services.hotkeys import (
    HOTKEY_ORDER,
    action_label,
    get_hotkey,
    reset_hotkeys,
    set_hotkey,
)
from app.ui.key_capture import KeyCaptureButton
from app.ui.widgets import SlideBackButton
from app.services.settings import (
    get_alpha_matting,
    get_export_custom_ext,
    get_export_format,
    get_export_prefix,
    get_model,
    get_theme,
    set_alpha_matting,
    set_export_custom_ext,
    set_export_format,
    set_export_prefix,
    set_model,
    set_theme,
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
        for name in ("外观", "模型选择", "导出", "快捷键"):
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
        form.addRow("", self._hint("跟随系统时，会随 Windows 浅色/深色自动切换。"))
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

            title = QLabel(action_label(aid))
            title.setObjectName("HotkeyActionTitle")
            title.setMinimumWidth(72)
            title.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )

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

            row.addWidget(title, 1)
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
        self.btn_reset_hotkeys.setToolTip("将可自定义快捷键还原为默认")
        self.btn_reset_hotkeys.clicked.connect(self._on_reset_hotkeys)
        reset_row.addWidget(self.btn_reset_hotkeys)
        lay.addLayout(reset_row)

        # Fixed / mouse actions (not rebindable)
        fixed = [
            ("固定操作（不可改）", [
                ("Esc", "关闭灯箱；设置页不退出（请点「返回」）"),
                ("← / →", "灯箱上一张 / 下一张"),
            ]),
            ("对照（单张预览）", [
                ("左键长按（单图）", "显示原图；松开恢复结果"),
                ("左键长按（并排）", "该侧原位换成另一张；松开恢复"),
                ("Space 按住", "单图看原图；并排时切换右侧（结果侧）"),
                ("「左右对照」按钮", "左原图 / 右结果并排"),
                ("左键拖移", "拖出结果文件（优先于长按）"),
            ]),
            ("多图 / 灯箱", [
                ("点击缩略图", "进入单张预览（灯箱）"),
                ("右键", "返回网格"),
            ]),
        ]
        for section, items in fixed:
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
