"""PipelineWorker: runs an OCRPipeline on a background thread and reports through Qt signals."""
from __future__ import annotations

import logging
import traceback

from PySide6.QtCore import QThread, Signal

from core.models import OCRResult, PageJob, RunOptions
from core.pipeline import OCRPipeline
from core.progress import ProgressUpdate

log = logging.getLogger(__name__)


class PipelineWorker(QThread):
    """Adapter between the Qt-free core and the UI.

    Signals: ``progress(ProgressUpdate)``, ``resultReady(OCRResult)``, ``failed(message, traceback)`` and
    ``ended(status)`` with status 'done', 'cancelled' or 'failed' (always emitted last).
    """

    progress = Signal(object)
    resultReady = Signal(object)
    failed = Signal(str, str)
    ended = Signal(str)

    def __init__(self, pipeline: OCRPipeline, path: str, jobs: list[PageJob], options: RunOptions) -> None:
        super().__init__()
        self._pipeline, self._path, self._jobs, self._options = pipeline, path, jobs, options

    def cancel(self) -> None:
        """Ask the pipeline to stop after the current page."""
        self._pipeline.cancel()

    def run(self) -> None:
        """Thread body: run the pipeline and translate its outcome into signals."""
        status = "failed"
        try:
            completed = self._pipeline.run(self._path, self._jobs, self._options,
                                           self.progress.emit, self.resultReady.emit)
            status = "done" if completed else "cancelled"
        except Exception as ex:  # noqa: BLE001 - surfaced in the UI
            details = traceback.format_exc()
            log.error("OCR run failed:\n%s", details)
            self.failed.emit(str(ex).strip() or ex.__class__.__name__, details)
        finally:
            self.ended.emit(status)
