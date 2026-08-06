"""Star-button about / support panel — style from 尺寸.png (☆ popup).

Layout under title-bar ☆:
  [ QQ交流群:… ]
  [ 反馈 - 建议(B站私信) ]
  [ 反馈 - 建议(Github Issues) ]
  caption
  [ 图+阴影 ] [ 图+阴影 ]
  [  微信   ] [  支付宝  ]   ← labels BELOW images (never on top)

Window: translucent outer shell + rounded card (no black corner rect).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPixmap,
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

from app.runtime_paths import bundle_root
from app.ui.button_fx import apply_soft_button_shadow


# ── Content ───────────────────────────────────────────────────
QQ_GROUP = "912291243"
BILI_URL = (
    "https://space.bilibili.com/3546651731953873?spm_id_from=333.40164.0.0"
)
# Public GitHub Issues — anyone can open bug reports / feature suggestions
GITHUB_ISSUES_URL = "https://github.com/wyf-777/win-bg-tool/issues"
CAPTION = "o(´^｀)o你不会想白嫖吧"

# Panel width ≈ 尺寸.png left popup; height follows content (must fit QR + labels)
_PANEL_W = 360
_QR_SIDE = 140
# Soft corner radius on QR tiles (slight round, not too pill-like)
_QR_RADIUS = 6
_BTN_H = 40
# Space between image bottom and label
_QR_LABEL_GAP = 12
_LABEL_H = 20
# Outer margin so drop-shadow is not clipped
_SHADOW_PAD = 18


def _assets_dir() -> Path:
    candidates = [
        Path(__file__).resolve().parents[1] / "assets",
        bundle_root() / "app" / "assets",
        bundle_root() / "assets",
    ]
    for p in candidates:
        if p.is_dir():
            return p
    return candidates[0]


def _load_qr_pixmap(name: str, side: int = _QR_SIDE) -> QPixmap:
    path = _assets_dir() / f"{name}_qr.png"
    pm = QPixmap(str(path)) if path.is_file() else QPixmap()
    if pm.isNull():
        pm = QPixmap(side, side)
        pm.fill(Qt.GlobalColor.white)
    else:
        pm = pm.scaled(
            side,
            side,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Center-crop to exact square if aspect differed
        if pm.width() != side or pm.height() != side:
            x = max(0, (pm.width() - side) // 2)
            y = max(0, (pm.height() - side) // 2)
            pm = pm.copy(x, y, side, side)
    return _round_clip_pixmap(pm, side, _QR_RADIUS)


def _round_clip_pixmap(src: QPixmap, side: int, radius: int) -> QPixmap:
    """
    Soft AA rounded-rect clip.

    Avoid setClipPath-only and QRegion masks (both look faceted / "straight").
    Use DestinationIn with an antialiased rounded alpha mask instead.
    """
    # Half-pixel inset keeps AA samples inside the bitmap
    rect = QRectF(0.5, 0.5, float(side - 1), float(side - 1))
    r = float(max(1, radius))

    # 1) AA alpha mask
    mask = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    mask.fill(0)
    mp = QPainter(mask)
    mp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    mp.setPen(Qt.PenStyle.NoPen)
    mp.setBrush(QColor(255, 255, 255, 255))
    path = QPainterPath()
    path.addRoundedRect(rect, r, r)
    mp.drawPath(path)
    mp.end()

    # 2) Draw source, then punch with mask for smooth corner falloff
    out_img = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    out_img.fill(0)
    op = QPainter(out_img)
    op.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    op.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    # White base so transparent QR assets still look solid
    op.fillRect(0, 0, side, side, QColor("#ffffff"))
    op.drawPixmap(0, 0, src)
    op.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    op.drawImage(0, 0, mask)
    op.end()
    return QPixmap.fromImage(out_img)


class StarAboutPanel(QWidget):
    """Frameless popup under ☆ — layout matches 尺寸.png."""

    closed = Signal()
    status = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setObjectName("StarAboutPanelShell")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        shell = QVBoxLayout(self)
        shell.setContentsMargins(
            _SHADOW_PAD, _SHADOW_PAD, _SHADOW_PAD, _SHADOW_PAD
        )
        shell.setSpacing(0)

        self._card = QFrame()
        self._card.setObjectName("StarAboutPanel")
        self._card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._card.setFixedWidth(_PANEL_W)
        # Height from content — never crush QR labels onto images
        self._card.setMinimumHeight(400)
        self._card.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum
        )

        card_l = QVBoxLayout(self._card)
        card_l.setContentsMargins(20, 16, 20, 14)
        card_l.setSpacing(10)

        self.btn_qq = self._row_btn(f"QQ交流群:{QQ_GROUP}")
        self.btn_qq.setToolTip("点击复制群号到剪贴板")
        self.btn_qq.clicked.connect(self._on_qq)

        self.btn_bili = self._row_btn("反馈 - 建议(B站私信)")
        self.btn_bili.setToolTip("打开 B 站主页（可私信反馈）")
        self.btn_bili.clicked.connect(
            lambda: self._open_url(BILI_URL, "已打开 B 站主页")
        )

        self.btn_gh = self._row_btn("反馈 - 建议(Github Issues)")
        self.btn_gh.setToolTip(
            "打开 GitHub Issues：提交 Bug、功能建议（需 GitHub 账号）"
        )
        self.btn_gh.clicked.connect(
            lambda: self._open_url(
                GITHUB_ISSUES_URL,
                "已打开 GitHub Issues（可提建议 / 反馈问题）",
            )
        )

        for b in (self.btn_qq, self.btn_bili, self.btn_gh):
            card_l.addWidget(b, 0)

        cap = QLabel(CAPTION)
        cap.setObjectName("StarAboutCaption")
        cap.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        cap.setFixedHeight(24)
        card_l.addWidget(cap, 0)

        # QR row: two independent columns (image then label under it)
        qr_row = QHBoxLayout()
        qr_row.setSpacing(20)
        # Tighter vertical padding above/below the image pair
        qr_row.setContentsMargins(0, 4, 0, 2)
        qr_row.addStretch(1)
        qr_row.addWidget(self._qr_tile("wechat", "微信"), 0, Qt.AlignmentFlag.AlignTop)
        qr_row.addWidget(self._qr_tile("alipay", "支付宝"), 0, Qt.AlignmentFlag.AlignTop)
        qr_row.addStretch(1)
        card_l.addLayout(qr_row)

        apply_soft_button_shadow(self._card, level="float")
        shell.addWidget(self._card)

        self.setFixedWidth(_PANEL_W + 2 * _SHADOW_PAD)
        self.adjustSize()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_Source
        )
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)

    def _row_btn(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("StarAboutBtn")
        btn.setFixedHeight(_BTN_H)
        btn.setMinimumHeight(_BTN_H)
        btn.setMaximumHeight(_BTN_H)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        apply_soft_button_shadow(btn, level="control")
        return btn

    def _qr_tile(self, asset: str, label: str) -> QWidget:
        """
        尺寸.png:
          square image with soft shadow, then caption centered under it
          (label must not sit on the image).
        """
        col = QWidget()
        col.setObjectName("StarQrColumn")
        col.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Reserve full vertical space: image + gap + label (+ small shadow bleed)
        col_h = _QR_SIDE + _QR_LABEL_GAP + _LABEL_H + 6
        col.setFixedSize(_QR_SIDE + 16, col_h)
        col.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        lay = QVBoxLayout(col)
        lay.setContentsMargins(8, 2, 8, 2)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        host = QFrame()
        host.setObjectName("StarQrImageHost")
        host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        host.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        host.setFixedSize(_QR_SIDE, _QR_SIDE)
        host.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        img = QLabel(host)
        img.setObjectName("StarQrImage")
        img.setGeometry(0, 0, _QR_SIDE, _QR_SIDE)
        img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img.setPixmap(_load_qr_pixmap(asset, _QR_SIDE))
        img.setScaledContents(False)
        img.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Mature dark elevation: soft ambient (not ink blob); white tile + rim
        apply_soft_button_shadow(host, level="tile")
        lay.addWidget(host, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(_QR_LABEL_GAP)

        lab = QLabel(label)
        lab.setObjectName("StarQrCaption")
        lab.setFixedHeight(_LABEL_H)
        lab.setFixedWidth(_QR_SIDE)
        lab.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        lab.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        lay.addWidget(lab, 0, Qt.AlignmentFlag.AlignHCenter)

        return col

    def popup_at(self, global_pos) -> None:
        self.adjustSize()
        x = int(global_pos.x()) - 4 - _SHADOW_PAD
        y = int(global_pos.y()) + 6 - _SHADOW_PAD
        screen = QGuiApplication.screenAt(global_pos)
        if screen is not None:
            geo = screen.availableGeometry()
            if x + self.width() > geo.right() - 8:
                x = geo.right() - self.width() - 8
            if y + self.height() > geo.bottom() - 8:
                y = int(global_pos.y()) - self.height() + _SHADOW_PAD - 6
            if x < geo.left() + 8:
                x = geo.left() + 8
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    def _on_qq(self) -> None:
        # Only copy group number — keep panel open so user can still use other actions
        QGuiApplication.clipboard().setText(QQ_GROUP)
        self.status.emit(f"已复制 QQ 群号 {QQ_GROUP}，可到 QQ 中搜索加群")

    def _open_url(self, url: str, msg: str) -> None:
        QDesktopServices.openUrl(QUrl(url))
        self.status.emit(msg)
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit()
        super().closeEvent(event)
