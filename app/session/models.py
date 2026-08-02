from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from PIL import Image


class ItemStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class ImageItem:
    source_path: Path
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: ItemStatus = ItemStatus.QUEUED
    result_image: Optional[Image.Image] = None
    result_path: Optional[Path] = None  # temp PNG for drag-out / export
    error: Optional[str] = None
    selected: bool = False

    @property
    def name(self) -> str:
        return self.source_path.name

    @property
    def is_terminal(self) -> bool:
        return self.status in (ItemStatus.DONE, ItemStatus.FAILED)
