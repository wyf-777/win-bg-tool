"""Alpha-mask editing primitives used by the manual repair screen."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

from PIL import Image, ImageChops, ImageDraw, ImageFilter


@dataclass(frozen=True)
class LassoSelection:
    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class BrushSelection:
    points: tuple[tuple[float, float], ...]
    radius: float


Selection = Union[LassoSelection, BrushSelection]
EditOperation = Literal["keep", "erase", "restore"]


def selection_mask(
    size: tuple[int, int], selection: Selection, feather: int = 0
) -> Image.Image:
    """Create an L-mode selection mask, optionally softened in image pixels."""
    width, height = size
    if width <= 0 or height <= 0:
        raise ValueError("image size must be positive")

    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    if isinstance(selection, LassoSelection) and len(selection.points) >= 3:
        draw.polygon(selection.points, fill=255)
    elif isinstance(selection, BrushSelection):
        if not selection.points:
            raise ValueError("brush selection needs at least one point")
        radius = max(0.5, float(selection.radius))
        if len(selection.points) > 1:
            draw.line(
                selection.points,
                fill=255,
                width=max(1, round(radius * 2)),
                joint="curve",
            )
        for x, y in selection.points:
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
    else:
        raise ValueError("lasso selection needs at least three points")

    radius = max(0, int(feather))
    if radius:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=radius))
    return mask


def apply_mask_edit(
    original: Image.Image,
    current: Image.Image,
    selection: Selection,
    operation: EditOperation,
    feather: int = 0,
) -> Image.Image:
    """Apply one selection operation and return a new RGBA image.

    ``keep`` and ``erase`` preserve the current RGB pixels and only edit alpha.
    ``restore`` blends pixels back from the original image and restores opacity.
    """
    if original.size != current.size:
        raise ValueError("original and current images must have the same size")

    original_rgba = original.convert("RGBA")
    current_rgba = current.convert("RGBA")
    mask = selection_mask(current_rgba.size, selection, feather)
    alpha = current_rgba.getchannel("A")

    if operation == "keep":
        new_alpha = ImageChops.multiply(alpha, mask)
        result = current_rgba.copy()
        result.putalpha(new_alpha)
        return result
    if operation == "erase":
        inverse = ImageChops.invert(mask)
        new_alpha = ImageChops.multiply(alpha, inverse)
        result = current_rgba.copy()
        result.putalpha(new_alpha)
        return result
    if operation == "restore":
        result = Image.composite(original_rgba, current_rgba, mask)
        result.putalpha(ImageChops.lighter(alpha, mask))
        return result
    raise ValueError(f"unsupported mask edit operation: {operation}")


class MaskEditHistory:
    """Bounded image-snapshot history for a single editing session."""

    def __init__(self, original: Image.Image, current: Image.Image, limit: int = 15) -> None:
        if original.size != current.size:
            raise ValueError("original and current images must have the same size")
        self.original = original.convert("RGBA")
        self.current = current.convert("RGBA")
        self.limit = max(1, int(limit))
        self._undo: list[Image.Image] = []
        self._redo: list[Image.Image] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def apply(self, selection: Selection, operation: EditOperation, feather: int) -> Image.Image:
        self._undo.append(self.current.copy())
        if len(self._undo) > self.limit:
            self._undo.pop(0)
        self._redo.clear()
        self.current = apply_mask_edit(
            self.original, self.current, selection, operation, feather
        )
        return self.current

    def undo(self) -> Image.Image:
        if not self._undo:
            return self.current
        self._redo.append(self.current.copy())
        self.current = self._undo.pop()
        return self.current

    def redo(self) -> Image.Image:
        if not self._redo:
            return self.current
        self._undo.append(self.current.copy())
        self.current = self._redo.pop()
        return self.current

    def replace_current(self, image: Image.Image) -> Image.Image:
        """Replace the visible result without creating another history entry."""
        self.current = image.convert("RGBA")
        return self.current
