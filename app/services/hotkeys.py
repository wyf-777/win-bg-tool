"""User-configurable keyboard shortcuts (Valorant-style rebinding)."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QSettings
from PySide6.QtGui import QKeySequence

from app.services.settings import APP, ORG

# action_id → (label_zh, description_zh, default portable sequence)
HOTKEY_DEFS: Dict[str, Tuple[str, str, str]] = {
    "open": ("打开图片", "从文件选择并添加要去背景的图片", "Ctrl+O"),
    "export": ("导出结果", "保存处理结果（单图另存 / 多图批量导出）", "Ctrl+S"),
    "copy": ("复制结果", "把当前结果图复制到系统剪贴板，可到别处粘贴", "Ctrl+C"),
    "paste": ("粘贴图片", "从剪贴板导入图片并加入处理", "Ctrl+V"),
    "settings": ("打开设置", "进入设置页（外观、模型、导出、快捷键）", "Ctrl+,"),
}

HOTKEY_ORDER: List[str] = ["open", "export", "copy", "paste", "settings"]

KEY_PREFIX = "hotkeys/"


def _settings() -> QSettings:
    return QSettings(ORG, APP)


def default_sequence(action_id: str) -> str:
    return HOTKEY_DEFS.get(action_id, ("", "", ""))[2]


def action_label(action_id: str) -> str:
    return HOTKEY_DEFS.get(action_id, (action_id, "", ""))[0]


def action_description(action_id: str) -> str:
    return HOTKEY_DEFS.get(action_id, ("", "", ""))[1]


def normalize_sequence(seq: str) -> str:
    """Portable string form, empty if invalid."""
    s = (seq or "").strip()
    if not s:
        return ""
    qs = QKeySequence(s)
    if qs.isEmpty():
        return ""
    # PortableText is stable across locales for storage
    return qs.toString(QKeySequence.SequenceFormat.PortableText)


def display_sequence(seq: str) -> str:
    s = normalize_sequence(seq)
    if not s:
        return "未设置"
    return QKeySequence(s).toString(QKeySequence.SequenceFormat.NativeText)


def get_hotkey(action_id: str) -> str:
    if action_id not in HOTKEY_DEFS:
        return ""
    raw = _settings().value(KEY_PREFIX + action_id, default_sequence(action_id))
    s = normalize_sequence(str(raw) if raw is not None else "")
    return s if s else default_sequence(action_id)


def get_all_hotkeys() -> Dict[str, str]:
    return {aid: get_hotkey(aid) for aid in HOTKEY_ORDER}


def set_hotkey(action_id: str, sequence: str) -> Tuple[bool, str]:
    """
    Save binding. Returns (ok, message).
    Rejects empty / invalid / conflicts with another action.
    """
    if action_id not in HOTKEY_DEFS:
        return False, "未知操作。"
    s = normalize_sequence(sequence)
    if not s:
        return False, "无效按键。"

    # Conflict?
    for other in HOTKEY_ORDER:
        if other == action_id:
            continue
        if get_hotkey(other) == s:
            return (
                False,
                f"与「{action_label(other)}」冲突（{display_sequence(s)}）。",
            )

    st = _settings()
    st.setValue(KEY_PREFIX + action_id, s)
    st.sync()
    return True, f"已设置：{action_label(action_id)} → {display_sequence(s)}"


def reset_hotkeys() -> None:
    st = _settings()
    for aid in HOTKEY_ORDER:
        st.setValue(KEY_PREFIX + aid, default_sequence(aid))
    st.sync()


def find_action_by_sequence(sequence: str) -> Optional[str]:
    s = normalize_sequence(sequence)
    if not s:
        return None
    for aid in HOTKEY_ORDER:
        if get_hotkey(aid) == s:
            return aid
    return None


def sequence_matches_event(sequence: str, event) -> bool:
    """True if *event* (QKeyEvent) equals the stored portable *sequence*."""
    s = normalize_sequence(sequence)
    if not s:
        return False
    try:
        ev = QKeySequence(event.keyCombination())
    except Exception:
        return False
    if ev.isEmpty():
        return False
    return normalize_sequence(
        ev.toString(QKeySequence.SequenceFormat.PortableText)
    ) == s
