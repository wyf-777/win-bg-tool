from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence, Tuple

from PIL import Image

# (id, label, pillow_format, default_suffix, supports_alpha)
EXPORT_FORMATS: Sequence[Tuple[str, str, str, str, bool]] = (
    ("png", "PNG（推荐，保留透明）", "PNG", ".png", True),
    ("webp", "WebP（可透明，体积较小）", "WEBP", ".webp", True),
    ("jpg", "JPEG（不透明，体积小）", "JPEG", ".jpg", False),
    ("bmp", "BMP（不透明）", "BMP", ".bmp", False),
    ("tiff", "TIFF（可透明）", "TIFF", ".tiff", True),
    ("custom", "自定义扩展名…", "PNG", ".png", True),
)

DEFAULT_EXPORT_FORMAT = "png"
KNOWN_FORMAT_IDS = {f[0] for f in EXPORT_FORMATS}


def format_info(fmt_id: str) -> Tuple[str, str, str, bool]:
    """Return (pillow_format, suffix, label, supports_alpha)."""
    for fid, label, pfmt, suffix, alpha in EXPORT_FORMATS:
        if fid == fmt_id:
            return pfmt, suffix, label, alpha
    return "PNG", ".png", "PNG", True


def normalize_custom_ext(ext: str) -> str:
    text = (ext or "").strip().lower().lstrip(".")
    text = "".join(c for c in text if c.isalnum())
    if not text:
        return "png"
    return text[:8]


def resolve_export_format(
    fmt_id: str, custom_ext: str = ""
) -> Tuple[str, str, bool]:
    """
    Returns (pillow_format, suffix_with_dot, supports_alpha).
    """
    fmt_id = (fmt_id or DEFAULT_EXPORT_FORMAT).lower()
    if fmt_id == "custom":
        ext = normalize_custom_ext(custom_ext)
        # guess pillow format from extension
        mapping = {
            "png": ("PNG", True),
            "jpg": ("JPEG", False),
            "jpeg": ("JPEG", False),
            "webp": ("WEBP", True),
            "bmp": ("BMP", False),
            "tif": ("TIFF", True),
            "tiff": ("TIFF", True),
            "gif": ("GIF", True),
        }
        pfmt, alpha = mapping.get(ext, ("PNG", True))
        return pfmt, f".{ext}", alpha
    pfmt, suffix, _label, alpha = format_info(fmt_id)
    return pfmt, suffix, alpha


def _prepare_image(image: Image.Image, *, supports_alpha: bool) -> Image.Image:
    if supports_alpha:
        return image if image.mode == "RGBA" else image.convert("RGBA")
    # Flatten onto white for JPEG/BMP etc.
    rgba = image if image.mode == "RGBA" else image.convert("RGBA")
    bg = Image.new("RGB", rgba.size, (255, 255, 255))
    bg.paste(rgba, mask=rgba.split()[-1])
    return bg


def export_image(
    image: Image.Image,
    dest: Path | str,
    *,
    fmt_id: str = DEFAULT_EXPORT_FORMAT,
    custom_ext: str = "",
    prefix: str = "",
    source_name: Optional[str] = None,
) -> Path:
    """Save image using configured format. dest may be file path or directory."""
    pfmt, suffix, supports_alpha = resolve_export_format(fmt_id, custom_ext)
    dest_path = Path(dest)

    if dest_path.is_dir() or str(dest).endswith(("/", "\\")):
        base = source_name or "image"
        stem = Path(base).stem
        name = f"{prefix}{stem}{suffix}" if prefix else f"{stem}_nobg{suffix}"
        dest_path = dest_path / name
    else:
        dest_path = dest_path.with_suffix(suffix)
        if prefix and not dest_path.name.startswith(prefix):
            dest_path = dest_path.with_name(f"{prefix}{dest_path.name}")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    img = _prepare_image(image, supports_alpha=supports_alpha)
    save_kw = {}
    if pfmt == "JPEG":
        save_kw["quality"] = 92
    elif pfmt == "WEBP":
        save_kw["quality"] = 90
    img.save(dest_path, format=pfmt, **save_kw)
    return dest_path.resolve()


def export_png(
    image: Image.Image,
    dest: Path | str,
    *,
    prefix: str = "",
    source_name: Optional[str] = None,
) -> Path:
    """Backward-compatible PNG export."""
    return export_image(
        image,
        dest,
        fmt_id="png",
        prefix=prefix,
        source_name=source_name,
    )


def file_filter_for_format(fmt_id: str, custom_ext: str = "") -> str:
    if fmt_id == "custom":
        ext = normalize_custom_ext(custom_ext)
        return f"自定义 (*.{ext});;所有文件 (*.*)"
    _pfmt, suffix, label, _alpha = format_info(fmt_id)
    # simplify filter name
    short = suffix.lstrip(".").upper()
    return f"{short} 图片 (*{suffix});;所有文件 (*.*)"
