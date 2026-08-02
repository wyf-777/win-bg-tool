from __future__ import annotations

import sys
from pathlib import Path


def _ensure_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def main() -> int:
    _ensure_path()
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from app.engines.local_rembg import cleanup_interrupted_downloads
    from app.ui.main_window import MainWindow

    # Drop leftover pooch tmp* from last interrupted model download
    # (prevents clutter; next download starts clean once)
    try:
        cleanup_interrupted_downloads()
    except Exception:
        pass

    # High-DPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Peel")
    app.setOrganizationName("win-bg-tool")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
