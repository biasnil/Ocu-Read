"""Abstract base class every OCR engine implements."""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod

from PIL import Image

from core.models import OCRResult, Region, RunOptions
from core.progress import StageReporter, noop_stage


class OCREngine(ABC):
    """An OCR backend.

    Lifecycle: the pipeline calls :meth:`prepare` once (load / download models), then :meth:`run` per page.
    :meth:`cancel` may be called from another thread; engines stop as soon as they safely can
    (between pages or between internal steps - a model call already in flight can't be interrupted).
    """

    label: str = "engine"

    def __init__(self) -> None:
        self._cancel = threading.Event()
        self.report: StageReporter = noop_stage   # set by the pipeline: report(stage, fraction | None)

    @abstractmethod
    def prepare(self) -> None:
        """Load (and if needed download) the models. Raises RuntimeError with a helpful message on failure."""

    @abstractmethod
    def run(self, image: Image.Image, regions: list[Region], options: RunOptions) -> OCRResult:
        """OCR one page image. ``regions`` are in the image's pixel coordinates; honour ``options.only``."""

    def cancel(self) -> None:
        """Ask the engine to stop."""
        self._cancel.set()

    def reset_cancel(self) -> None:
        """Clear a previous cancel request (called at the start of each run)."""
        self._cancel.clear()

    @property
    def cancelled(self) -> bool:
        """True once :meth:`cancel` has been called."""
        return self._cancel.is_set()
