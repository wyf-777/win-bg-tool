"""Load images for preview (original vs result)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


def load_preview_image(path: Path | str) -> Image.Image:
    """Load image as RGB/RGBA with EXIF orientation fixed."""
    p = Path(path)
    img = Image.open(p)
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    return img
