"""Copy result images to the system clipboard (F10 / Ctrl+C)."""

from __future__ import annotations

import sys
from typing import Tuple

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QMimeData
from PySide6.QtGui import QClipboard, QGuiApplication, QImage
from PIL import Image


def pil_to_qimage(image: Image.Image) -> QImage:
    rgba = image if image.mode == "RGBA" else image.convert("RGBA")
    w, h = rgba.size
    raw = rgba.tobytes("raw", "RGBA")
    qimg = QImage(raw, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
    return qimg.convertToFormat(QImage.Format.Format_ARGB32)


def _encode(qimg: QImage, fmt: str) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    if not qimg.save(buf, fmt):
        return b""
    buf.close()
    return bytes(ba)


def copy_pil_image(image: Image.Image) -> Tuple[bool, str]:
    """
    Put a PIL image on the clipboard for paste into Paint / Word / Explorer.
    Prefer native Windows clipboard APIs; fall back to Qt.
    """
    if image is None:
        return False, "没有可复制的图片。"

    try:
        qimg = pil_to_qimage(image)
        if qimg.isNull():
            return False, "图片转换失败。"

        png = _encode(qimg, "PNG")
        if not png:
            return False, "编码 PNG 失败。"

        # Windows: write system clipboard ourselves (most reliable for non-Qt apps)
        if sys.platform == "win32":
            if _win32_set_clipboard_image(qimg, png):
                return True, "已复制到剪贴板，可在其他软件中粘贴（Ctrl+V）。"

        # Qt fallback
        clip = QGuiApplication.clipboard()
        if clip is None:
            return False, "无法访问系统剪贴板。"

        mime = QMimeData()
        mime.setImageData(qimg)
        mime.setData("PNG", QByteArray(png))
        mime.setData("image/png", QByteArray(png))
        clip.clear(QClipboard.Mode.Clipboard)
        clip.setMimeData(mime, QClipboard.Mode.Clipboard)

        if clip.image(QClipboard.Mode.Clipboard).isNull() and not (
            clip.mimeData() and clip.mimeData().hasImage()
        ):
            return False, "复制后剪贴板仍为空，请重试。"
        return True, "已复制到剪贴板，可在其他软件中粘贴（Ctrl+V）。"
    except Exception as exc:
        return False, f"复制失败：{exc}"


def _win32_set_clipboard_image(qimg: QImage, png: bytes) -> bool:
    """
    OpenClipboard + EmptyClipboard, then set:
      - CF_DIB (from BMP without 14-byte file header) for Paint etc.
      - registered format \"PNG\" for Office / modern apps
    """
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        GMEM_MOVEABLE = 0x0002
        CF_DIB = 8

        # BMP → DIB (skip BITMAPFILEHEADER 14 bytes)
        bmp = _encode(qimg, "BMP")
        if len(bmp) <= 14:
            return False
        dib = bmp[14:]

        CF_PNG = user32.RegisterClipboardFormatW("PNG")

        def _set_data(fmt: int, data: bytes) -> bool:
            h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not h:
                return False
            ptr = kernel32.GlobalLock(h)
            if not ptr:
                kernel32.GlobalFree(h)
                return False
            ctypes.memmove(ptr, data, len(data))
            kernel32.GlobalUnlock(h)
            if not user32.SetClipboardData(fmt, h):
                kernel32.GlobalFree(h)
                return False
            return True

        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            ok_dib = _set_data(CF_DIB, dib)
            ok_png = bool(CF_PNG) and _set_data(CF_PNG, png)
            return bool(ok_dib or ok_png)
        finally:
            user32.CloseClipboard()
    except Exception:
        return False
