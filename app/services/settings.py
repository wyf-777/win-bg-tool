from __future__ import annotations

from PySide6.QtCore import QSettings

from app.engines.models_catalog import DEFAULT_MODEL_ID, is_known_model
from app.services.export import (
    DEFAULT_EXPORT_FORMAT,
    KNOWN_FORMAT_IDS,
    normalize_custom_ext,
)

ORG = "win-bg-tool"
APP = "Peel"

KEY_THEME = "ui/theme"
KEY_MODEL = "engine/model"
KEY_EXPORT_PREFIX = "export/prefix"
KEY_EXPORT_FORMAT = "export/format"
KEY_EXPORT_CUSTOM_EXT = "export/custom_ext"
KEY_ALPHA_MATTING = "engine/alpha_matting"
KEY_PREFER_ACCEL = "engine/prefer_accel"  # F14: soft GPU preference
KEY_WATCH_ENABLED = "watch/enabled"
KEY_WATCH_DIR = "watch/dir"
KEY_WATCH_OUTPUT_DIR = "watch/output_dir"  # empty → {watch}/已抠图
KEY_WATCH_PROCESS_EXISTING = "watch/process_existing"
KEY_WATCH_RECURSIVE = "watch/recursive"
KEY_WATCH_ARCHIVE = "watch/archive_sources"
KEY_WATCH_TRAY = "watch/minimize_to_tray"

DEFAULT_THEME = "system"
DEFAULT_EXPORT_PREFIX = "nobg_"
DEFAULT_ALPHA_MATTING = False
DEFAULT_CUSTOM_EXT = "png"
DEFAULT_PREFER_ACCEL = False  # everyone starts on safe CPU path
DEFAULT_WATCH_ENABLED = False
# Default on: folder often already has images when user clicks 应用
DEFAULT_WATCH_PROCESS_EXISTING = True
DEFAULT_WATCH_RECURSIVE = False
DEFAULT_WATCH_ARCHIVE = False
DEFAULT_WATCH_TRAY = True  # when watch on, close goes to tray


def settings() -> QSettings:
    return QSettings(ORG, APP)


def get_theme() -> str:
    value = str(settings().value(KEY_THEME, DEFAULT_THEME))
    if value not in {"light", "dark", "system"}:
        return DEFAULT_THEME
    return value


def set_theme(theme: str) -> None:
    if theme not in {"light", "dark", "system"}:
        theme = DEFAULT_THEME
    s = settings()
    s.setValue(KEY_THEME, theme)
    s.sync()


def get_model() -> str:
    value = str(settings().value(KEY_MODEL, DEFAULT_MODEL_ID))
    if not is_known_model(value):
        return DEFAULT_MODEL_ID
    return value


def set_model(model_id: str) -> None:
    if not is_known_model(model_id):
        model_id = DEFAULT_MODEL_ID
    s = settings()
    s.setValue(KEY_MODEL, model_id)
    s.sync()


def get_export_prefix() -> str:
    value = settings().value(KEY_EXPORT_PREFIX, DEFAULT_EXPORT_PREFIX)
    text = str(value) if value is not None else DEFAULT_EXPORT_PREFIX
    text = text.strip().replace("/", "_").replace("\\", "_")
    return text if text else DEFAULT_EXPORT_PREFIX


def set_export_prefix(prefix: str) -> None:
    text = (prefix or "").strip().replace("/", "_").replace("\\", "_")
    if not text:
        text = DEFAULT_EXPORT_PREFIX
    s = settings()
    s.setValue(KEY_EXPORT_PREFIX, text)
    s.sync()


def get_export_format() -> str:
    value = str(settings().value(KEY_EXPORT_FORMAT, DEFAULT_EXPORT_FORMAT)).lower()
    if value not in KNOWN_FORMAT_IDS:
        return DEFAULT_EXPORT_FORMAT
    return value


def set_export_format(fmt_id: str) -> None:
    fmt_id = (fmt_id or DEFAULT_EXPORT_FORMAT).lower()
    if fmt_id not in KNOWN_FORMAT_IDS:
        fmt_id = DEFAULT_EXPORT_FORMAT
    s = settings()
    s.setValue(KEY_EXPORT_FORMAT, fmt_id)
    s.sync()


def get_export_custom_ext() -> str:
    value = settings().value(KEY_EXPORT_CUSTOM_EXT, DEFAULT_CUSTOM_EXT)
    return normalize_custom_ext(str(value) if value is not None else DEFAULT_CUSTOM_EXT)


def set_export_custom_ext(ext: str) -> None:
    s = settings()
    s.setValue(KEY_EXPORT_CUSTOM_EXT, normalize_custom_ext(ext))
    s.sync()


def get_alpha_matting() -> bool:
    value = settings().value(KEY_ALPHA_MATTING, DEFAULT_ALPHA_MATTING)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes"}
    return bool(value)


def set_alpha_matting(enabled: bool) -> None:
    s = settings()
    s.setValue(KEY_ALPHA_MATTING, bool(enabled))
    s.sync()


def _as_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes"}
    if value is None:
        return default
    return bool(value)


def get_prefer_accel() -> bool:
    """User wants faster processing when the machine supports it (soft preference)."""
    return _as_bool(
        settings().value(KEY_PREFER_ACCEL, DEFAULT_PREFER_ACCEL),
        DEFAULT_PREFER_ACCEL,
    )


def set_prefer_accel(enabled: bool) -> None:
    s = settings()
    s.setValue(KEY_PREFER_ACCEL, bool(enabled))
    s.sync()


def get_watch_enabled() -> bool:
    return _as_bool(
        settings().value(KEY_WATCH_ENABLED, DEFAULT_WATCH_ENABLED),
        DEFAULT_WATCH_ENABLED,
    )


def set_watch_enabled(enabled: bool) -> None:
    s = settings()
    s.setValue(KEY_WATCH_ENABLED, bool(enabled))
    s.sync()


def get_watch_dir() -> str:
    value = settings().value(KEY_WATCH_DIR, "")
    return str(value).strip() if value is not None else ""


def set_watch_dir(path: str) -> None:
    s = settings()
    s.setValue(KEY_WATCH_DIR, (path or "").strip())
    s.sync()


def get_watch_output_dir() -> str:
    """Empty string means default {watch}/已抠图."""
    value = settings().value(KEY_WATCH_OUTPUT_DIR, "")
    return str(value).strip() if value is not None else ""


def set_watch_output_dir(path: str) -> None:
    s = settings()
    s.setValue(KEY_WATCH_OUTPUT_DIR, (path or "").strip())
    s.sync()


def get_watch_process_existing() -> bool:
    return _as_bool(
        settings().value(KEY_WATCH_PROCESS_EXISTING, DEFAULT_WATCH_PROCESS_EXISTING),
        DEFAULT_WATCH_PROCESS_EXISTING,
    )


def set_watch_process_existing(enabled: bool) -> None:
    s = settings()
    s.setValue(KEY_WATCH_PROCESS_EXISTING, bool(enabled))
    s.sync()


def get_watch_recursive() -> bool:
    return _as_bool(
        settings().value(KEY_WATCH_RECURSIVE, DEFAULT_WATCH_RECURSIVE),
        DEFAULT_WATCH_RECURSIVE,
    )


def set_watch_recursive(enabled: bool) -> None:
    s = settings()
    s.setValue(KEY_WATCH_RECURSIVE, bool(enabled))
    s.sync()


def get_watch_archive_sources() -> bool:
    return _as_bool(
        settings().value(KEY_WATCH_ARCHIVE, DEFAULT_WATCH_ARCHIVE),
        DEFAULT_WATCH_ARCHIVE,
    )


def set_watch_archive_sources(enabled: bool) -> None:
    s = settings()
    s.setValue(KEY_WATCH_ARCHIVE, bool(enabled))
    s.sync()


def get_watch_tray() -> bool:
    return _as_bool(
        settings().value(KEY_WATCH_TRAY, DEFAULT_WATCH_TRAY),
        DEFAULT_WATCH_TRAY,
    )


def set_watch_tray(enabled: bool) -> None:
    s = settings()
    s.setValue(KEY_WATCH_TRAY, bool(enabled))
    s.sync()
