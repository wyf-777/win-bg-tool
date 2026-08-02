"""Click-to-rebind key capture button (Valorant-style)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QKeyEvent, QFocusEvent, QMouseEvent
from PySide6.QtWidgets import QPushButton


class KeyCaptureButton(QPushButton):
    """
    Idle: shows current shortcut.
    Click: enter capture mode ("请按键…").
    Next key chord becomes the new binding (signal captured).
    Esc cancels capture.
    """

    captured = Signal(str)  # portable sequence
    capture_cancelled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("KeyCaptureBtn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumWidth(120)
        self.setMinimumHeight(32)
        self._sequence = ""
        self._recording = False
        self.setToolTip("点击后按下想要的快捷键")

    def sequence(self) -> str:
        return self._sequence

    def set_sequence(self, seq: str) -> None:
        self._sequence = seq or ""
        if not self._recording:
            self._refresh_label()

    def is_recording(self) -> bool:
        return self._recording

    def start_capture(self) -> None:
        self._recording = True
        self.setText("请按键…")
        self.setProperty("recording", True)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.grabKeyboard()

    def stop_capture(self, *, emit_cancel: bool = False) -> None:
        if not self._recording:
            return
        self._recording = False
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        self.setProperty("recording", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self._refresh_label()
        if emit_cancel:
            self.capture_cancelled.emit()

    def _refresh_label(self) -> None:
        if self._sequence:
            self.setText(
                QKeySequence(self._sequence).toString(
                    QKeySequence.SequenceFormat.NativeText
                )
            )
        else:
            self.setText("未设置")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self._recording:
                self.stop_capture(emit_cancel=True)
            else:
                self.start_capture()
            event.accept()
            return
        super().mousePressEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        if self._recording:
            self.stop_capture(emit_cancel=True)
        super().focusOutEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if not self._recording:
            super().keyPressEvent(event)
            return
        if event.isAutoRepeat():
            event.accept()
            return

        key = event.key()
        # Esc is a valid bindable key (e.g. 「关闭/返回」). Cancel capture via
        # click-again or focus-out instead of Esc-to-cancel.

        # Ignore pure modifiers
        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
            Qt.Key.Key_AltGr,
            Qt.Key.Key_unknown,
        ):
            event.accept()
            return

        try:
            seq = QKeySequence(event.keyCombination())
        except Exception:
            # Fallback
            seq = QKeySequence(event.modifiers() | Qt.Key(key))  # type: ignore[operator]

        portable = seq.toString(QKeySequence.SequenceFormat.PortableText)
        if not portable or seq.isEmpty():
            event.accept()
            return

        self._sequence = portable
        self.stop_capture(emit_cancel=False)
        self.captured.emit(portable)
        event.accept()
