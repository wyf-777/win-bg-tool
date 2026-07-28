from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from PIL import Image


@dataclass
class EngineResult:
    """Result of a background-removal run."""

    image: Image.Image  # RGBA
    model_name: str
    source_path: Optional[Path] = None


class BackgroundEngine(ABC):
    """Unified interface for local / future online engines."""

    @abstractmethod
    def remove(
        self,
        source: Union[str, Path, bytes, Image.Image],
        *,
        source_path: Optional[Path] = None,
    ) -> EngineResult:
        raise NotImplementedError

    @abstractmethod
    def warmup(self) -> None:
        """Load model into memory (optional but recommended at startup)."""
        raise NotImplementedError

    @property
    @abstractmethod
    def model_name(self) -> str:
        raise NotImplementedError
