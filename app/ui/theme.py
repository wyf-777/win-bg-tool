from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class ThemeColors:
    name: str  # light | dark
    window_bg: str
    text: str
    muted: str
    card_bg: str
    card_border: str
    card_drag_bg: str
    card_drag_border: str
    button_bg: str
    button_border: str
    button_hover: str
    button_pressed: str
    button_disabled_bg: str
    button_disabled_text: str
    primary: str
    primary_hover: str
    primary_pressed: str
    primary_disabled: str
    checker_a: str
    checker_b: str
    accent_dash: str
    error_text: str


LIGHT = ThemeColors(
    name="light",
    window_bg="#f5f5f7",
    text="#1d1d1f",
    muted="#6e6e73",
    card_bg="#ffffff",
    card_border="#e5e5ea",
    card_drag_bg="#f0fff4",
    card_drag_border="#34c759",
    button_bg="#ffffff",
    button_border="#d2d2d7",
    button_hover="#fafafa",
    button_pressed="#f0f0f2",
    button_disabled_bg="#f5f5f7",
    button_disabled_text="#a1a1a6",
    primary="#34c759",
    primary_hover="#2fb350",
    primary_pressed="#248a3d",
    primary_disabled="#a8e6b4",
    checker_a="#e6e6e8",
    checker_b="#ffffff",
    accent_dash="#34c759",
    error_text="#c0392b",
)

DARK = ThemeColors(
    name="dark",
    # Material-style dark: hierarchy via surface lift more than ink shadows
    window_bg="#1c1c1e",
    text="#f5f5f7",
    muted="#98989d",
    # Elevated surfaces slightly lighter than window (Material overlay idea)
    card_bg="#2c2c2e",
    card_border="#48484a",
    card_drag_bg="#1e3a28",
    card_drag_border="#30d158",
    # Chrome / controls: one step above window for readable elevation without sludge
    button_bg="#3a3a3c",
    button_border="#636366",
    button_hover="#48484a",
    button_pressed="#2c2c2e",
    button_disabled_bg="#2c2c2e",
    button_disabled_text="#636366",
    primary="#30d158",
    primary_hover="#28c44c",
    primary_pressed="#1f9a3a",
    primary_disabled="#1f6b35",
    checker_a="#3a3a3c",
    checker_b="#2c2c2e",
    accent_dash="#30d158",
    error_text="#ff6b6b",
)


def system_is_dark() -> bool:
    """Read OS color scheme. Safe / cheap — no polling loop."""
    app = QApplication.instance()
    if app is not None:
        hints = app.styleHints()
        scheme = hints.colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
    # Fallback via palette
    gui = QGuiApplication.instance()
    if gui is not None:
        return gui.palette().color(gui.palette().ColorRole.Window).lightness() < 128
    return False


def resolve_theme(preference: str) -> ThemeColors:
    pref = (preference or "system").lower()
    if pref == "light":
        return LIGHT
    if pref == "dark":
        return DARK
    # system
    return DARK if system_is_dark() else LIGHT


def build_stylesheet(c: ThemeColors) -> str:
    from app.ui.button_fx import BUTTON_H, BUTTON_RADIUS

    bh = BUTTON_H
    # Same corner as 快捷键 KeyCaptureBtn / main-window capsules
    chrome_r = BUTTON_RADIUS
    br = BUTTON_RADIUS
    return f"""
    QMainWindow, QWidget {{
        background: {c.window_bg};
        color: {c.text};
        font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
        font-size: 13px;
    }}
    /* Labels must stay transparent so emoji/title/hints have no box behind them */
    QLabel {{
        background: transparent;
        border: none;
    }}
    /* Checkboxes must not inherit solid QWidget fill (looks like a grey box) */
    QCheckBox {{
        background: transparent;
        border: none;
        spacing: 6px;
        color: {c.text};
    }}
    QCheckBox:disabled {{
        color: {c.button_disabled_text};
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {c.button_border};
        background: {c.card_bg};
    }}
    QCheckBox::indicator:hover {{
        border-color: {c.primary};
    }}
    QCheckBox::indicator:checked {{
        background: {c.primary};
        border-color: {c.primary};
        image: none;
    }}
    QCheckBox::indicator:disabled {{
        background: {c.button_disabled_bg};
        border-color: {c.button_border};
    }}
    #BatchCheck, #TileCheck {{
        background: transparent;
        border: none;
    }}
    /* Frameless title strip — same fill as window (no OS caption seam) */
    #WindowTitleBar {{
        background: {c.window_bg};
        border: none;
    }}
    #MainCentral {{
        background: {c.window_bg};
    }}
    /* Window ☆ ⚙ ← – □ × : identical size / fill / shadow host (× uses WinCloseBtn) */
    QPushButton#WinChromeBtn,
    QPushButton#WinCloseBtn {{
        min-width: {bh}px;
        max-width: {bh}px;
        min-height: {bh}px;
        max-height: {bh}px;
        padding: 0;
        margin: 0;
        border-radius: {chrome_r}px;
        background: {c.button_bg};
        border: 1px solid {c.card_border};
        color: {c.muted};
        font-size: 14px;
        font-weight: 500;
    }}
    QPushButton#WinChromeBtn:hover,
    QPushButton#WinCloseBtn:hover {{
        background: {c.button_hover};
        border-color: {c.button_border};
        color: {c.text};
    }}
    QPushButton#WinChromeBtn:pressed,
    QPushButton#WinCloseBtn:pressed {{
        background: {c.button_pressed};
    }}
    /* Icon host inside chrome buttons — no second fill behind gear/arrow */
    QPushButton#WinChromeBtn QWidget#SlideSettingsIcon,
    QPushButton#WinCloseBtn QWidget#SlideSettingsIcon {{
        background: transparent;
        border: none;
    }}
    #ModelLabel {{
        color: {c.muted};
        font-size: 12px;
        background: transparent;
    }}
    #DropCanvas {{
        background: {c.card_bg};
        border: 1px solid {c.card_border};
        border-radius: 22px;
    }}
    #DropCanvas[dragOver="true"] {{
        background: {c.card_drag_bg};
        border: 1px solid {c.card_drag_border};
    }}
    #HeroEmoji, #HeroTitle, #HeroHint, #DragOutHint, #PreviewLabel {{
        background: transparent;
        border: none;
    }}
    #HeroTitle {{
        font-size: 28px;
        font-weight: 700;
        color: {c.text};
    }}
    #HeroHint, #DragOutHint, #FootHint {{
        color: {c.muted};
        font-size: 13px;
        background: transparent;
    }}
    #HeroHint[errorState="true"] {{
        color: {c.error_text};
    }}
    #DragOutHint {{
        font-size: 12px;
        margin-top: 2px;
        padding: 2px 8px;
        background: transparent;
    }}
    #LightboxChrome {{
        background: transparent;
        border: none;
        min-height: {bh}px;
        max-height: {bh}px;
    }}
    QPushButton#LightboxNavBtn {{
        min-width: {bh}px;
        max-width: {bh}px;
        min-height: {bh}px;
        max-height: {bh}px;
        padding: 0;
        border-radius: {chrome_r}px;
    }}
    /* Global buttons: height matches title-bar × */
    QPushButton {{
        background: {c.button_bg};
        border: 1px solid {c.card_border};
        border-radius: {chrome_r}px;
        padding: 0 14px;
        min-width: 72px;
        min-height: {bh}px;
        max-height: {bh}px;
        color: {c.text};
    }}
    QPushButton:hover {{
        background: {c.button_hover};
        border-color: {c.button_border};
        color: {c.text};
    }}
    QPushButton:pressed {{
        background: {c.button_pressed};
        border-color: {c.button_border};
    }}
    QPushButton:disabled {{
        color: {c.button_disabled_text};
        background: {c.button_disabled_bg};
        border-color: {c.card_border};
    }}
    /* Primary fill — same height as title-bar × */
    QPushButton#PrimaryBtn {{
        background: {c.primary};
        border: 1px solid {c.primary};
        color: #ffffff;
        font-weight: 600;
        min-width: 100px;
        min-height: {bh}px;
        max-height: {bh}px;
        padding: 0 16px;
        border-radius: {br}px;
    }}
    QPushButton#PrimaryBtn:hover {{
        background: {c.primary_hover};
        border-color: {c.primary_hover};
        color: #ffffff;
    }}
    QPushButton#PrimaryBtn:pressed {{
        background: {c.primary_pressed};
        border-color: {c.primary_pressed};
        color: #ffffff;
    }}
    QPushButton#PrimaryBtn:disabled {{
        background: {c.primary_disabled};
        border-color: {c.primary_disabled};
        color: #ffffff;
    }}
    QComboBox {{
        background: {c.button_bg};
        border: 1px solid {c.button_border};
        border-radius: 8px;
        padding: 4px 10px;
        min-width: 108px;
        color: {c.text};
    }}
    QComboBox:hover {{
        background: {c.button_hover};
    }}
    QComboBox QAbstractItemView {{
        background: {c.card_bg};
        color: {c.text};
        selection-background-color: {c.primary};
        border: 1px solid {c.card_border};
    }}
    QStatusBar {{
        background: transparent;
        color: {c.muted};
    }}
    QMenu {{
        background: {c.card_bg};
        color: {c.text};
        border: 1px solid {c.card_border};
    }}
    QMenu::item:selected {{
        background: {c.button_hover};
    }}
    QDialog {{
        background: {c.window_bg};
        color: {c.text};
    }}
    QGroupBox {{
        background: {c.card_bg};
        border: 1px solid {c.card_border};
        border-radius: 12px;
        margin-top: 12px;
        padding: 12px 12px 10px 12px;
        font-weight: 600;
        color: {c.text};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: {c.text};
    }}
    #SettingsHint {{
        color: {c.muted};
        font-size: 12px;
        font-weight: 400;
        background: transparent;
    }}
    QPushButton#SettingsBtn {{
        min-width: 72px;
        min-height: {bh}px;
        max-height: {bh}px;
        padding: 0 14px;
    }}
    /* Bottom action buttons — height = title-bar × */
    QPushButton#ActionBtn {{
        min-width: 72px;
        min-height: {bh}px;
        max-height: {bh}px;
        padding: 0 14px;
        border-radius: {br}px;
        background: {c.button_bg};
        border: 1px solid {c.card_border};
        color: {c.text};
        font-weight: 500;
    }}
    QPushButton#ActionBtn:hover {{
        background: {c.button_hover};
        border-color: {c.button_border};
        color: {c.text};
    }}
    QPushButton#ActionBtn:pressed {{
        background: {c.button_pressed};
        border-color: {c.button_border};
    }}
    QPushButton#ActionBtn:disabled {{
        color: {c.button_disabled_text};
        background: {c.button_disabled_bg};
        border-color: {c.card_border};
    }}
    QPushButton#CompactBtn {{
        min-width: 72px;
        max-width: 120px;
        min-height: {bh}px;
        max-height: {bh}px;
        padding: 0 12px;
        border-radius: {chrome_r}px;
    }}
    QPushButton#KeyCaptureBtn {{
        min-width: 120px;
        min-height: {bh}px;
        max-height: {bh}px;
        padding: 0 14px;
        border-radius: {chrome_r}px;
        background: {c.button_bg};
        border: 1px solid {c.card_border};
        color: {c.text};
        font-weight: 600;
    }}
    QPushButton#KeyCaptureBtn:hover {{
        border-color: {c.button_border};
        background: {c.button_hover};
        color: {c.text};
    }}
    QPushButton#KeyCaptureBtn:pressed {{
        background: {c.button_pressed};
        border-color: {c.button_border};
    }}
    QPushButton#KeyCaptureBtn[recording="true"] {{
        border-color: {c.primary};
        background: {c.card_drag_bg};
        color: {c.text};
    }}
    /* Settings controls — must override global QPushButton min/max or CJK clips */
    QPushButton#SettingsCtrlBtn {{
        min-width: 0px;
        min-height: {bh}px;
        max-height: 48px;
        padding: 0 16px;
        border-radius: {chrome_r}px;
        background: {c.button_bg};
        border: 1px solid {c.card_border};
        color: {c.text};
        font-size: 13px;
        font-weight: 600;
        text-align: center;
    }}
    QPushButton#SettingsCtrlBtn:hover {{
        border-color: {c.button_border};
        background: {c.button_hover};
        color: {c.text};
    }}
    QPushButton#SettingsCtrlBtn:pressed {{
        background: {c.button_pressed};
        border-color: {c.button_border};
    }}
    QPushButton#SettingsCtrlBtn:disabled {{
        color: {c.button_disabled_text};
        background: {c.button_disabled_bg};
        border-color: {c.card_border};
    }}
    /* 浏览 / 用默认 — custom width; height = 清空队列 ({bh}) */
    QPushButton#SettingsPathSideBtn {{
        min-width: 96px;
        max-width: 96px;
        min-height: {bh}px;
        max-height: {bh}px;
        padding: 0 14px;
        border-radius: {chrome_r}px;
        background: {c.button_bg};
        border: 1px solid {c.card_border};
        color: {c.text};
        font-size: 13px;
        font-weight: 600;
        text-align: center;
    }}
    QPushButton#SettingsPathSideBtn:hover {{
        border-color: {c.button_border};
        background: {c.button_hover};
        color: {c.text};
    }}
    QPushButton#SettingsPathSideBtn:pressed {{
        background: {c.button_pressed};
        border-color: {c.button_border};
    }}
    /* 应用 / 关闭应用 / 恢复默认 — custom width; height = 清空队列 */
    QPushButton#SettingsFooterBtn {{
        min-width: 112px;
        max-width: 112px;
        min-height: {bh}px;
        max-height: {bh}px;
        padding: 0 14px;
        border-radius: {chrome_r}px;
        background: {c.button_bg};
        border: 1px solid {c.card_border};
        color: {c.text};
        font-size: 13px;
        font-weight: 600;
        text-align: center;
    }}
    QPushButton#SettingsFooterBtn:hover {{
        border-color: {c.button_border};
        background: {c.button_hover};
        color: {c.text};
    }}
    QPushButton#SettingsFooterBtn:pressed {{
        background: {c.button_pressed};
        border-color: {c.button_border};
    }}
    /* Path field — same height as 清空队列 / side chips */
    QLineEdit#SettingsPathEdit {{
        min-height: {bh}px;
        max-height: {bh}px;
        padding: 0 12px;
        border-radius: {chrome_r}px;
        background: {c.button_bg};
        border: 1px solid {c.card_border};
        color: {c.text};
        font-size: 13px;
        selection-background-color: {c.primary};
        selection-color: #ffffff;
    }}
    QLineEdit#SettingsPathEdit:read-only {{
        background: {c.button_bg};
        color: {c.text};
    }}
    QLineEdit#SettingsPathEdit:focus {{
        border-color: {c.button_border};
    }}
    /* ☆ about / support panel (他的2.png)
       Outer shell is translucent; only the inner card is opaque + rounded. */
    #StarAboutPanelShell {{
        background: transparent;
        border: none;
    }}
    #StarAboutPanel {{
        background: {c.card_bg};
        border: 1px solid {c.card_border};
        border-radius: 14px;
    }}
    QPushButton#StarAboutBtn {{
        min-height: 40px;
        max-height: 40px;
        padding: 0 14px;
        border-radius: 12px;
        background: {c.button_bg};
        border: 1px solid {c.card_border};
        color: {c.text};
        font-weight: 500;
        font-size: 14px;
    }}
    QPushButton#StarAboutBtn:hover {{
        background: {c.button_hover};
        border-color: {c.button_border};
        color: {c.text};
    }}
    QPushButton#StarAboutBtn:pressed {{
        background: {c.button_pressed};
        border-color: {c.button_border};
    }}
    #StarAboutCaption {{
        color: {c.muted};
        font-size: 14px;
        background: transparent;
        border: none;
        padding: 2px 0 2px 0;
    }}
    /* QR tile: white rounded square + soft shadow (立体感)
       Dark: stronger rim so the tile lifts off dark panel (shadow alone is weak). */
    #StarQrColumn {{
        background: transparent;
        border: none;
    }}
    #StarQrImageHost {{
        background: transparent;
        /* Soft rim (not a heavy frame) — aids dark elevation without ink shadow */
        border: 1px solid {c.button_border};
        border-radius: 6px;
    }}
    #StarQrImage {{
        background: transparent;
        border: none;
        border-radius: 6px;
    }}
    /* Label on vertical axis under image */
    #StarQrCaption {{
        color: {c.muted};
        font-size: 13px;
        font-weight: 500;
        background: transparent;
        border: none;
        padding: 0;
    }}
    /* Fixed mouse-gesture badge: same chrome as KeyCaptureBtn + shadow; not clickable */
    QLabel#HotkeyGestureBadge {{
        min-width: 120px;
        min-height: {bh}px;
        max-height: {bh}px;
        padding: 0 14px;
        border-radius: {chrome_r}px;
        background: {c.button_bg};
        border: 1px solid {c.card_border};
        color: {c.muted};
        font-size: 13px;
        font-weight: 600;
    }}
    QFrame#HotkeySeparator {{
        background: {c.card_border};
        border: none;
        max-height: 1px;
        margin: 4px 0;
    }}
    #HotkeyActionTitle {{
        font-size: 14px;
        font-weight: 600;
        color: {c.text};
        background: transparent;
        border: none;
        padding: 0;
    }}
    #HotkeyActionDesc {{
        font-size: 12px;
        color: {c.muted};
        background: transparent;
        border: none;
        padding: 0;
    }}
    /* Selection strip — secondary zone (壹印-style param row) */
    #BatchBar {{
        background: {c.card_bg};
        border: 1px solid {c.card_border};
        border-radius: 12px;
    }}
    #BatchInfoLabel {{
        color: {c.muted};
        font-size: 12px;
        background: transparent;
        border: none;
    }}
    #MainActionsBar {{
        background: transparent;
        border: none;
        min-height: {bh}px;
    }}
    #MainFooter {{
        background: transparent;
        border: none;
    }}
    /* Capsule settings — host is transparent; shell scales inside */
    #SlideSettingsHost {{
        background: transparent;
        border: none;
    }}
    #SlideSettingsSlot {{
        background: transparent;
        border: none;
    }}
    #SlideExportText {{
        background: transparent;
        border: none;
        color: #ffffff;
        font-size: 13px;
        font-weight: 600;
    }}
    /* Shell is self-painted as a round pill; keep QSS transparent */
    #SlideSettingsBtn {{
        background: transparent;
        border: none;
    }}
    #SlideSettingsText {{
        font-size: 13px;
        font-weight: 500; /* reference font-medium */
        letter-spacing: -0.2px; /* tracking-tight */
        color: {c.text};
        background: transparent;
        border: none;
        padding: 0;
    }}
    /* Must override global QWidget {{ background }} so icons are not boxed */
    QWidget#SlideSettingsIcon,
    #SlideSettingsIcon {{
        color: {c.text};
        background: transparent;
        border: none;
        padding: 0;
    }}
    QWidget#SlideSettingsSlot,
    #SlideSettingsSlot {{
        background: transparent;
        border: none;
    }}
    /* Edge-style full-window settings (back lives in title-bar chrome) */
    #SettingsPage {{
        background: {c.window_bg};
    }}
    #SettingsChromeHost {{
        background: transparent;
        border: none;
        margin: 0;
        padding: 0;
    }}
    #SettingsTitle {{
        font-size: 18px;
        font-weight: 600;
        color: {c.text};
        background: transparent;
    }}
    #SettingsBackBtn {{
        min-width: 72px;
        padding: 6px 14px;
        border-radius: 8px;
    }}
    #SettingsNav {{
        background: {c.card_bg};
        border: none;
        border-right: 1px solid {c.card_border};
        padding: 12px 8px;
        outline: none;
    }}
    #SettingsNav::item {{
        padding: 10px 14px;
        border-radius: 8px;
        color: {c.text};
        margin: 2px 4px;
    }}
    #SettingsNav::item:selected {{
        background: {c.primary};
        color: #ffffff;
    }}
    #SettingsNav::item:hover:!selected {{
        background: {c.button_hover};
    }}
    #SettingsStack, #SettingsDetailPage, #SettingsDetailScroll {{
        background: {c.window_bg};
        border: none;
    }}
    #SettingsDetailScroll > QWidget > QWidget {{
        background: {c.window_bg};
    }}
    #SettingsFieldLabel {{
        font-size: 13px;
        font-weight: 600;
        color: {c.text};
        background: transparent;
        margin-top: 4px;
    }}
    /* Model guidance content uses the shared FAQ accordion row styling. */
    #ModelGuideLead,
    #ModelGuideFooter {{
        color: {c.muted};
        font-size: 12px;
        background: transparent;
    }}
    #ModelGuideTag {{
        color: {c.primary};
        background: {c.button_hover};
        border: 1px solid {c.card_border};
        border-radius: 6px;
        padding: 5px 8px;
        font-size: 12px;
        font-weight: 600;
    }}
    #ModelGuideText {{
        color: {c.text};
        font-size: 12px;
        background: transparent;
    }}
    /* FAQ accordion — no panel chrome (no fill / no outer box) */
    #FaqPanel {{
        background: transparent;
        border: none;
    }}
    #FaqListHost {{
        background: transparent;
        border: none;
    }}
    #FaqListScroll {{
        background: transparent;
        border: none;
    }}
    #FaqListScroll > QWidget > QWidget {{
        background: transparent;
    }}
    #FaqAccordionItem {{
        background: transparent;
        border: none;
        border-bottom: 1px solid {c.card_border};
        border-radius: 0;
    }}
    #FaqAccordionHeader {{
        background: transparent;
        border: none;
        min-height: 44px;
    }}
    #FaqAccordionHeader:hover {{
        background: transparent;
        color: {c.primary};
    }}
    #FaqAccordionTitle {{
        color: {c.text};
        font-size: 13px;
        font-weight: 500;
        background: transparent;
        border: none;
    }}
    #FaqAccordionChevron {{
        color: {c.muted};
        font-size: 16px;
        font-weight: 600;
        background: transparent;
        border: none;
    }}
    #FaqAccordionBody {{
        background: transparent;
        border: none;
    }}
    #FaqAccordionBodyText {{
        color: {c.muted};
        font-size: 13px;
        font-weight: 400;
        background: transparent;
        border: none;
        line-height: 1.5;
    }}
    #SettingsBodyText {{
        font-size: 13px;
        color: {c.muted};
        background: {c.card_bg};
        border: 1px solid {c.card_border};
        border-radius: 10px;
        padding: 12px 14px;
        line-height: 1.45;
    }}
    QTextEdit#SettingsBodyText {{
        font-size: 13px;
        color: {c.muted};
        background: {c.card_bg};
        border: 1px solid {c.card_border};
        border-radius: 10px;
        padding: 8px 10px;
        selection-background-color: {c.primary};
    }}
    QTextEdit#SettingsBodyText:focus {{
        border: 1px solid {c.card_border};
    }}
    /* F09: 结果 / 原图 对照切换 */
    #CompareBar {{
        background: transparent;
    }}
    QPushButton#CompareBtn {{
        min-width: 72px;
        min-height: {bh}px;
        max-height: {bh}px;
        padding: 0 12px;
        font-size: 13px;
        font-weight: 600;
        border: 1px solid {c.card_border};
        background: {c.card_bg};
        color: {c.muted};
        border-radius: {chrome_r}px;
        margin: 0 2px;
    }}
    QPushButton#CompareBtn:checked {{
        background: {c.primary};
        color: #ffffff;
        border-color: {c.primary};
    }}
    QPushButton#CompareBtn:hover:!checked {{
        color: {c.text};
        border-color: {c.button_border};
        background: {c.button_hover};
    }}
    QPushButton#CompareBtn:pressed:!checked {{
        background: {c.button_pressed};
        border-color: {c.button_border};
    }}
    QPushButton#CompareBtn:disabled {{
        color: {c.button_disabled_text};
        background: {c.button_disabled_bg};
    }}
    /* Minimal repair workspace: command bar above, contextual tools at left. */
    #WatchStatusLabel {{
        color: {c.primary};
        font-size: 12px;
        font-weight: 600;
        background: transparent;
        padding: 2px 8px;
    }}
    #RepairPage {{
        background: {c.window_bg};
    }}
    #RepairTopBar {{
        background: {c.card_bg};
        border: none;
        border-bottom: 1px solid {c.card_border};
    }}
    #RepairTitle {{
        font-size: 15px;
        font-weight: 600;
        color: {c.text};
        background: transparent;
    }}
    #RepairSidebar {{
        background: {c.card_bg};
        border: 1px solid {c.card_border};
        border-radius: 10px;
    }}
    #RepairSidebarContent,
    QScrollArea#RepairSidebar > QWidget > QWidget {{
        background: {c.card_bg};
    }}
    #RepairSectionLabel {{
        color: {c.muted};
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.4px;
        background: transparent;
        padding: 0 2px 2px 2px;
    }}
    #RepairSliderLabel {{
        color: {c.text};
        font-size: 12px;
        background: transparent;
        padding: 0 2px;
    }}
    #RepairSliderBlock {{
        background: transparent;
    }}
    /* Override global QPushButton min-width:88 — narrow sidebar needs 0. */
    QPushButton#RepairToolBtn,
    QPushButton#RepairActionBtn,
    QPushButton#RepairClearBtn {{
        min-width: 0;
        max-width: 16777215;
        min-height: {bh}px;
        max-height: {bh}px;
        padding: 0 10px;
        border-radius: {chrome_r}px;
        text-align: center;
    }}
    QPushButton#RepairToolBtn:checked {{
        background: {c.primary};
        border-color: {c.primary};
        color: #ffffff;
        font-weight: 600;
    }}
    QPushButton#RepairToolBtn:hover:!checked,
    QPushButton#RepairActionBtn:hover,
    QPushButton#RepairClearBtn:hover {{
        background: {c.button_hover};
        border-color: {c.button_border};
        color: {c.text};
    }}
    QPushButton#RepairToolBtn:pressed:!checked,
    QPushButton#RepairActionBtn:pressed,
    QPushButton#RepairClearBtn:pressed {{
        background: {c.button_pressed};
        border-color: {c.button_border};
    }}
    QPushButton#RepairToolBtn:disabled,
    QPushButton#RepairActionBtn:disabled,
    QPushButton#RepairClearBtn:disabled {{
        color: {c.button_disabled_text};
        background: {c.button_disabled_bg};
        border-color: {c.card_border};
    }}
    QPushButton#RepairActionBtn {{
        font-weight: 600;
    }}
    QPushButton#RepairClearBtn {{
        color: {c.muted};
    }}
    QPushButton#RepairBackBtn,
    QPushButton#RepairFinishBtn {{
        min-width: 72px;
        min-height: {bh}px;
        max-height: {bh}px;
        padding: 0 14px;
        border-radius: {chrome_r}px;
    }}
    QPushButton#RepairFinishBtn {{
        background: {c.primary};
        border-color: {c.primary};
        color: #ffffff;
        font-weight: 600;
    }}
    QPushButton#RepairFinishBtn:hover {{
        background: {c.primary_hover};
        border-color: {c.primary_hover};
        color: #ffffff;
    }}
    QPushButton#RepairFinishBtn:pressed {{
        background: {c.primary_hover};
        border-color: {c.primary_hover};
    }}
    /* Slider body transparent; track/handle must contrast with sidebar card. */
    QScrollArea#RepairSidebar QSlider {{
        background: transparent;
        border: none;
        min-height: 24px;
        margin: 2px 2px;
        padding: 0;
    }}
    QScrollArea#RepairSidebar QSlider::groove:horizontal {{
        height: 6px;
        border: none;
        border-radius: 3px;
        /* button_border, not disabled_bg — dark disabled_bg == card_bg (invisible). */
        background: {c.button_border};
    }}
    QScrollArea#RepairSidebar QSlider::sub-page:horizontal {{
        height: 6px;
        border: none;
        border-radius: 3px;
        background: {c.primary};
    }}
    QScrollArea#RepairSidebar QSlider::add-page:horizontal {{
        height: 6px;
        border: none;
        border-radius: 3px;
        background: {c.button_border};
    }}
    QScrollArea#RepairSidebar QSlider::handle:horizontal {{
        width: 16px;
        height: 16px;
        margin: -5px 0;
        border: 2px solid {c.card_bg};
        border-radius: 8px;
        background: {c.primary};
    }}
    QScrollArea#RepairSidebar QSlider::handle:horizontal:hover {{
        background: {c.primary_hover};
    }}
    """
