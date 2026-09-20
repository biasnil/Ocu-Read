"""OCRPipeline: orchestrates load -> mask/preprocess -> engine -> post-process for a list of pages."""
from __future__ import annotations

import dataclasses
import logging
from typing import Callable

from PIL import Image

from core.models import OCRResult, PageJob, Region, RunOptions
from core.ocr_engine import OCREngine
from core.postprocessing import PostProcessor
from core.preprocessing import Preprocessor, blank_ignored, build_ignore_mask
from core.progress import ProgressListener, ProgressTracker, ProgressUpdate, TqdmBridge
from fileio.file_loader import FileLoader

log = logging.getLogger(__name__)


class OCRPipeline:
    """Runs one engine over many pages. Pure Python (no Qt): the UI wraps it in a worker thread.
    A pipeline is single-use: build a new one for every run.

    Region handling: when rotate/deskew would move pixels, ignored areas are blanked on the original
    page first (so the regions still line up); otherwise the engine applies the regions itself.
    """

    def __init__(self, engine: OCREngine, preprocessor: Preprocessor, postprocessor: PostProcessor,
                 bridge: TqdmBridge | None = None) -> None:
        self.engine = engine
        self.preprocessor = preprocessor
        self.postprocessor = postprocessor
        self.bridge = bridge or TqdmBridge()
        self._cancelled = False
        self.engine.reset_cancel()   # engines are cached between runs; clear any stale cancel request now,
                                     # so a cancel that arrives before run() starts is never lost

    def cancel(self) -> None:
        """Stop after the page currently being processed."""
        self._cancelled = True
        self.engine.cancel()

    def run(self, path: str, jobs: list[PageJob], options: RunOptions, on_progress: ProgressListener,
            on_result: Callable[[OCRResult], None]) -> bool:
        """Process ``jobs`` in order. Returns True if the run completed, False if it was cancelled."""
        if self._cancelled:
            return False
        tracker = ProgressTracker(len(jobs), on_progress)
        self.engine.report = tracker.report
        with self.bridge.attached(tracker.on_tqdm):
            tracker.loading("Loading OCR engine\u2026", None)
            self.engine.prepare()
            log.info("Engine ready: %s", self.engine.label)
            with FileLoader(path) as loader:   # own handle: PyMuPDF objects aren't thread-safe
                for n, job in enumerate(jobs):
                    if self._cancelled:
                        return False
                    tracker.begin_page(n)
                    tracker.report("ocr", None)
                    image = loader.render(job.page_index, cache=False)
                    result = self._process_page(image, job, options, tracker)
                    on_result(result)
                    tracker.page_done()
        on_progress(ProgressUpdate("done", 1.0, "Done", "done"))
        return True

    def _process_page(self, image: Image.Image, job: PageJob, options: RunOptions,
                      tracker: ProgressTracker) -> OCRResult:
        regions: list[Region] = job.regions
        opts = options
        if self.preprocessor.changes_geometry:
            mask = build_ignore_mask(image.size, regions, options.only)
            image = blank_ignored(image, mask)
            regions, opts = [], dataclasses.replace(options, only=False)
        image = self.preprocessor.apply(image)
        result = self.engine.run(image, regions, opts)
        tracker.report("assemble", None)
        result = self.postprocessor.process(result, options)
        result.page_index = job.page_index
        return result
