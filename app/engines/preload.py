"""
Preload heavy inference imports before the main window is shown.

Importing rembg / onnxruntime / cv2 / numpy still briefly takes the GIL even
from a worker thread — that is the “卡一次” users feel mid-drag. Running the
import *before* window.show() moves that cost into startup wait, so interactive
use stays smooth.
"""

from __future__ import annotations

import threading
import traceback
from typing import Optional

_lock = threading.Lock()
_thread: Optional[threading.Thread] = None
_done = threading.Event()
_error: Optional[str] = None


def _preload_work() -> None:
    global _error
    try:
        # Order: leaf native stacks first, then rembg (pulls the rest)
        import numpy  # noqa: F401
        import cv2  # noqa: F401
        import onnxruntime  # noqa: F401
        from rembg.bg import remove  # noqa: F401
        from rembg.session_factory import new_session  # noqa: F401
        # Touch pooch lightly (used for model paths / download)
        import pooch  # noqa: F401
        # Note: do NOT create InferenceSession here — that can take many seconds
        # and would block first paint. Session load stays on the post-show worker.
    except Exception as exc:
        _error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    finally:
        _done.set()


def start_preload() -> None:
    """Kick off background import as early as possible (idempotent)."""
    global _thread
    with _lock:
        if _thread is not None:
            return
        _done.clear()
        _thread = threading.Thread(
            target=_preload_work,
            name="peel-preload-inference",
            daemon=True,
        )
        _thread.start()


def wait_preload(*, timeout: float = 180.0) -> Optional[str]:
    """
    Block until preload finishes. Returns error string or None on success.
    Safe to call if start_preload was never called (returns None immediately).
    """
    if _thread is None and not _done.is_set():
        # Synchronous path: run once on this thread
        _preload_work()
        return _error
    _done.wait(timeout=timeout)
    return _error


def preload_finished() -> bool:
    return _done.is_set()


def preload_error() -> Optional[str]:
    return _error
