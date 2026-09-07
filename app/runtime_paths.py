"""Resolve project / models paths for dev and frozen (PyInstaller) builds."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# Bundled lightweight model for offline first launch of packaged builds
BUNDLED_MODEL_ID = "u2netp"
BUNDLED_MODEL_FILE = f"{BUNDLED_MODEL_ID}.onnx"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """Writable app root: project root in dev, directory of the .exe when frozen."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    # app/runtime_paths.py → project root
    return Path(__file__).resolve().parents[1]


def bundle_root() -> Path:
    """Read-only resource root (PyInstaller _MEIPASS or project root)."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return app_root()
    return app_root()


_models_dir_cache: Path | None = None


def models_dir() -> Path:
    """
    Writable directory for ONNX models (U2NET_HOME).

    Frozen builds use the current user's Local AppData because the normal
    installer location (Program Files) is not writable after installation.
    Development builds continue to use project/models.

    Cached after first call so settings UI status probes do not mkdir every time.
    """
    global _models_dir_cache
    if _models_dir_cache is not None:
        return _models_dir_cache
    if is_frozen():
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            path = Path(local_app_data) / "Peel" / "models"
        else:
            path = Path.home() / "AppData" / "Local" / "Peel" / "models"
    else:
        path = app_root() / "models"
    path.mkdir(parents=True, exist_ok=True)
    _models_dir_cache = path
    return path


def ensure_bundled_models() -> None:
    """
    Copy shipped model weights from the package into the writable models dir.
    Packaged builds include U²-Net 轻量 (u2netp) by default.
    """
    dest_dir = models_dir()
    dest = dest_dir / BUNDLED_MODEL_FILE
    if dest.is_file() and dest.stat().st_size > 1024:
        return
    candidates = [
        bundle_root() / "models" / BUNDLED_MODEL_FILE,
        # Migration path for older frozen builds that stored models next to exe.
        app_root() / "models" / BUNDLED_MODEL_FILE,
    ]
    for src in candidates:
        try:
            if src.is_file() and src.stat().st_size > 1024:
                if src.resolve() == dest.resolve():
                    return
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                return
        except OSError:
            continue
