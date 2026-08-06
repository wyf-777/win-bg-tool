"""Shared elevation shadows — light / dark recipes from mature UI systems.

Design notes (Material dark theme + Fluent 2 elevation):
  - Light: soft low-opacity black, small Y offset, moderate blur.
  - Dark: black shadows alone fail on near-black surfaces. Mature apps
    combine (1) slightly lighter surface fills, (2) subtle rims, and
    (3) *soft* ambient shadows at ~25–45% opacity — not 80–100% ink blobs.
  - Prefer short offsets (1–4px) and controlled blur; huge Y/blur looks muddy.

Qt only supports one QGraphicsDropShadowEffect per widget, so each level
is a single carefully tuned layer (approximating dual-shadow systems).
"""

from __future__ import annotations

from typing import Literal

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QPushButton,
    QWidget,
)

# Unified control height — same as WindowControlButton (☆ – □ ×)
BUTTON_H = 32
# Soft rounded-rect corner (KeyCapture / SettingsCtrl / main capsules)
BUTTON_RADIUS = max(8, BUTTON_H // 3)  # 10 when H=32
BUTTON_PILL_RADIUS = BUTTON_H // 2

_PROP = "_peel_soft_btn_shadow"
_LEVEL_PROP = "_peel_shadow_level"

ShadowLevel = Literal["chrome", "control", "float", "tile"]

_dark = False


def set_button_shadow_theme(*, dark: bool) -> None:
    """Select light vs dark elevation recipe (call before polish/refresh)."""
    global _dark
    _dark = bool(dark)


def is_button_shadow_dark() -> bool:
    return _dark


def _shadow_recipe(
    level: ShadowLevel = "control",
) -> tuple[float, float, QColor]:
    """
    Returns (blur, offset_y, color) for a single-layer elevation.

    Levels (inspired by Fluent / Material control elevation):
      chrome  — title bar ☆ ⚙ – □ × (lowest, tight)
      control — capsules, settings buttons, key capture
      float   — popovers / about panel card
      tile    — QR image tiles (white cards; dark needs less ink)
    """
    # alpha is 0–255
    if not _dark:
        # Light: soft, airy — ~10–14% black, short drop
        table: dict[str, tuple[float, float, int]] = {
            "chrome": (8.0, 1.0, 26),  # ~10%
            "control": (10.0, 2.0, 32),  # ~12.5%
            "float": (18.0, 4.0, 38),  # ~15%
            "tile": (12.0, 2.0, 36),  # ~14%
        }
    else:
        # Dark: soft ambient, NOT pure black sludge
        # Fluent-ish: opacity ~28–40%, modest Y; avoid α≥200 + huge blur
        table = {
            "chrome": (10.0, 1.0, 90),  # ~35%
            "control": (12.0, 2.0, 100),  # ~39%
            "float": (20.0, 4.0, 110),  # ~43%
            "tile": (14.0, 2.0, 70),  # ~27% — white tile already pops
        }
    blur, oy, alpha = table.get(level, table["control"])
    return (blur, oy, QColor(0, 0, 0, alpha))


def make_soft_button_shadow(
    parent: QWidget | None = None,
    *,
    level: ShadowLevel = "control",
) -> QGraphicsDropShadowEffect:
    """Soft drop shadow for current theme + elevation level."""
    blur, oy, color = _shadow_recipe(level)
    shadow = QGraphicsDropShadowEffect(parent)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, oy)
    shadow.setColor(color)
    return shadow


def _configure_shadow(
    effect: QGraphicsDropShadowEffect,
    *,
    level: ShadowLevel = "control",
) -> None:
    blur, oy, color = _shadow_recipe(level)
    effect.setBlurRadius(blur)
    effect.setOffset(0, oy)
    effect.setColor(color)


def apply_soft_button_shadow(
    widget: QWidget,
    *,
    level: ShadowLevel = "control",
) -> None:
    """Attach / refresh soft shadow for the given elevation level."""
    if widget is None:
        return
    # Remember level for theme refresh
    widget.setProperty(_LEVEL_PROP, level)
    existing = widget.graphicsEffect()
    if isinstance(existing, QGraphicsDropShadowEffect):
        _configure_shadow(existing, level=level)
        widget.setProperty(_PROP, True)
        return
    widget.setGraphicsEffect(make_soft_button_shadow(widget, level=level))
    widget.setProperty(_PROP, True)


def refresh_soft_button_shadow(widget: QWidget) -> None:
    """Re-apply current theme recipe, preserving elevation level."""
    raw = widget.property(_LEVEL_PROP) if widget is not None else None
    level: ShadowLevel = raw if raw in (
        "chrome",
        "control",
        "float",
        "tile",
    ) else "control"
    apply_soft_button_shadow(widget, level=level)


def polish_button_tree(root: QWidget | None, *, refresh: bool = False) -> None:
    """
    Apply elevation shadows to:
      - all QPushButton (chrome level if Win* btn, else control)
      - capsule hosts (#SlideSettingsHost)
      - hotkey gesture badges (#HotkeyGestureBadge)
    """
    if root is None:
        return
    for btn in root.findChildren(QPushButton):
        name = btn.objectName()
        if name in ("WinChromeBtn", "WinCloseBtn"):
            lvl: ShadowLevel = "chrome"
        else:
            lvl = "control"
        if refresh:
            # Keep prior level if set, else assign by object name
            if not btn.property(_LEVEL_PROP):
                apply_soft_button_shadow(btn, level=lvl)
            else:
                refresh_soft_button_shadow(btn)
        else:
            apply_soft_button_shadow(btn, level=lvl)
    for w in root.findChildren(QWidget):
        name = w.objectName()
        if name in ("SlideSettingsHost", "HotkeyGestureBadge"):
            if refresh and w.property(_LEVEL_PROP):
                refresh_soft_button_shadow(w)
            else:
                apply_soft_button_shadow(w, level="control")
