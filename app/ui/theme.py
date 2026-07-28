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
    primary_disabled="#a8e6b4",
    checker_a="#e6e6e8",
    checker_b="#ffffff",
    accent_dash="#34c759",
    error_text="#c0392b",
)

DARK = ThemeColors(
    name="dark",
    window_bg="#1c1c1e",
    text="#f5f5f7",
    muted="#98989d",
    card_bg="#2c2c2e",
    card_border="#3a3a3c",
    card_drag_bg="#1e3a28",
    card_drag_border="#30d158",
    button_bg="#3a3a3c",
    button_border="#48484a",
    button_hover="#48484a",
    button_pressed="#636366",
    button_disabled_bg="#2c2c2e",
    button_disabled_text="#636366",
    primary="#30d158",
    primary_hover="#28c44c",
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
    #BrandLabel {{
        font-size: 18px;
        font-weight: 600;
        letter-spacing: 0.2px;
        color: {c.text};
        background: transparent;
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
        min-height: 36px;
        max-height: 44px;
    }}
    QPushButton#LightboxNavBtn {{
        min-width: 40px;
        max-width: 40px;
        min-height: 40px;
        max-height: 40px;
        padding: 0;
        border-radius: 12px;
    }}
    QPushButton {{
        background: {c.button_bg};
        border: 1px solid {c.button_border};
        border-radius: 10px;
        padding: 8px 16px;
        min-width: 88px;
        color: {c.text};
    }}
    QPushButton:hover {{
        background: {c.button_hover};
    }}
    QPushButton:pressed {{
        background: {c.button_pressed};
    }}
    QPushButton:disabled {{
        color: {c.button_disabled_text};
        background: {c.button_disabled_bg};
    }}
    QPushButton#PrimaryBtn {{
        background: {c.primary};
        border: none;
        color: white;
        font-weight: 600;
        min-width: 100px;
        padding: 0 18px;
        border-radius: 18px;
    }}
    QPushButton#PrimaryBtn:hover {{
        background: {c.primary_hover};
    }}
    QPushButton#PrimaryBtn:disabled {{
        background: {c.primary_disabled};
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
        padding: 6px 12px;
    }}
    /* Bottom action buttons — same height as open capsule (~36) */
    QPushButton#ActionBtn {{
        min-width: 72px;
        padding: 0 16px;
        border-radius: 18px;
        background: {c.button_bg};
        border: 1px solid {c.button_border};
        color: {c.text};
        font-weight: 500;
    }}
    QPushButton#ActionBtn:hover {{
        background: {c.button_hover};
        border-color: {c.primary};
    }}
    QPushButton#ActionBtn:disabled {{
        color: {c.button_disabled_text};
        background: {c.button_disabled_bg};
    }}
    QPushButton#CompactBtn {{
        min-width: 72px;
        max-width: 120px;
        padding: 6px 12px;
        border-radius: 10px;
    }}
    QPushButton#KeyCaptureBtn {{
        min-width: 120px;
        padding: 6px 14px;
        border-radius: 8px;
        background: {c.button_bg};
        border: 1px solid {c.button_border};
        color: {c.text};
        font-weight: 600;
    }}
    QPushButton#KeyCaptureBtn:hover {{
        border-color: {c.primary};
        background: {c.button_hover};
    }}
    QPushButton#KeyCaptureBtn[recording="true"] {{
        border-color: {c.primary};
        background: {c.card_drag_bg};
        color: {c.text};
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
        min-height: 40px;
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
    /* Edge-style full-window settings */
    #SettingsPage {{
        background: {c.window_bg};
    }}
    #SettingsTopBar {{
        background: {c.card_bg};
        border-bottom: 1px solid {c.card_border};
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
        padding: 4px 12px;
        font-size: 13px;
        font-weight: 600;
        border: 1px solid {c.card_border};
        background: {c.card_bg};
        color: {c.muted};
        border-radius: 8px;
        margin: 0 2px;
    }}
    QPushButton#CompareBtn:checked {{
        background: {c.primary};
        color: #ffffff;
        border-color: {c.primary};
    }}
    QPushButton#CompareBtn:hover:!checked {{
        color: {c.text};
        border-color: {c.primary};
        background: {c.button_hover};
    }}
    QPushButton#CompareBtn:disabled {{
        color: {c.button_disabled_text};
        background: {c.button_disabled_bg};
    }}
    """
