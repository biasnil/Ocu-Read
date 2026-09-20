"""Normal mode: PaddleOCR or docTR."""
from __future__ import annotations

import logging
import time
from typing import Any

from PIL import Image

from core.devices import resolve_paddle_device, resolve_torch_device
from core.languages import Language
from core.models import OCRResult, Region, RunOptions, TextBox
from core.ocr_engine import OCREngine
from core.preprocessing import build_ignore_mask, ignored_fraction

log = logging.getLogger(__name__)


class _PaddleBackend:
    name = "PaddleOCR"

    def __init__(self, language: Language, device: str | None) -> None:
        from paddleocr import PaddleOCR  # ImportError propagates to NormalEngine

        kwargs: dict = dict(use_doc_orientation_classify=False, use_doc_unwarping=False,
                            use_textline_orientation=False)
        if language.paddle_code:
            kwargs["lang"] = language.paddle_code
        if device:
            kwargs["device"] = device
        try:  # PaddleOCR 3.x
            self.ocr = PaddleOCR(**kwargs)
        except (TypeError, ValueError):  # PaddleOCR 2.x
            legacy: dict = dict(use_angle_cls=True, show_log=False)
            if language.paddle_code:
                legacy["lang"] = language.paddle_code
            if device:
                legacy["use_gpu"] = device != "cpu"
            self.ocr = PaddleOCR(**legacy)

    def detect(self, image: Image.Image) -> list[TextBox]:
        """Return one box per detected text line."""
        import numpy as np

        arr = np.ascontiguousarray(np.asarray(image.convert("RGB"))[:, :, ::-1])  # RGB -> BGR
        boxes: list[TextBox] = []

        def add(poly: Any, text: Any, score: Any) -> None:
            """Append one detection as a TextBox."""
            pts = np.asarray(poly, dtype=float).reshape(-1, 2)
            boxes.append(TextBox(pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max(),
                                 str(text), float(score)))

        if hasattr(self.ocr, "predict"):
            for res in self.ocr.predict(arr):
                for text, poly, score in zip(res["rec_texts"], res["rec_polys"], res["rec_scores"]):
                    add(poly, text, score)
        else:
            for page in self.ocr.ocr(arr, cls=True) or []:
                for poly, (text, score) in page or []:
                    add(poly, text, score)
        return boxes


class _DoctrBackend:
    name = "docTR"

    def __init__(self, device: str | None) -> None:
        from doctr.models import ocr_predictor

        self.model = ocr_predictor(pretrained=True)
        if device:
            try:
                self.model = self.model.to(device)
            except Exception:  # noqa: BLE001 - device move is best effort
                pass

    def detect(self, image: Image.Image) -> list[TextBox]:
        """Return one box per detected text line."""
        import numpy as np

        page = self.model([np.asarray(image.convert("RGB"))]).pages[0]
        h, w = page.dimensions
        boxes: list[TextBox] = []
        for block in page.blocks:
            for line in block.lines:
                (x0, y0), (x1, y1) = line.geometry
                words = line.words
                conf = sum(word.confidence for word in words) / max(1, len(words))
                boxes.append(TextBox(x0 * w, y0 * h, x1 * w, y1 * h,
                                     " ".join(word.value for word in words), float(conf)))
        return boxes


class NormalEngine(OCREngine):
    """Fast traditional OCR. Boxes that overlap an ignored area are dropped after detection."""

    def __init__(self, language: Language, backend: str = "auto", device: str = "auto") -> None:
        super().__init__()
        self.language, self.backend, self.device = language, backend, device
        self.label = "Normal OCR"
        self._impl: _PaddleBackend | _DoctrBackend | None = None

    def _make(self, name: str) -> _PaddleBackend | _DoctrBackend:
        if name == "paddle":
            dev, warn = resolve_paddle_device(self.device)
            if warn:
                log.warning(warn)
            return _PaddleBackend(self.language, dev)
        dev, warn = resolve_torch_device(self.device)
        if warn:
            log.warning(warn)
        if self.language.paddle_code not in (None, "en"):
            log.warning("docTR is tuned for Latin-script text; the language setting is ignored. "
                        "Use PaddleOCR for Korean / Chinese / Japanese.")
        return _DoctrBackend(dev)

    def prepare(self) -> None:
        """Import and build the chosen backend (Auto tries PaddleOCR, then docTR)."""
        if self._impl is not None:
            return
        order = {"auto": ["paddle", "doctr"], "paddle": ["paddle"], "doctr": ["doctr"]}[self.backend]
        errors: list[str] = []
        for name in order:
            try:
                self._impl = self._make(name)
                break
            except ImportError as ex:
                errors.append(f"{name}: {ex}")
                log.warning("Couldn't import %s: %s", name, ex)
        if self._impl is None:
            raise RuntimeError(
                "The selected Normal-mode engine isn't available.\n\n"
                "  pip install paddlepaddle==3.2.2 paddleocr\n"
                '  or: pip install "python-doctr[torch]"\n\n' + "\n".join(errors)
            )
        self.label = self._impl.name

    def run(self, image: Image.Image, regions: list[Region], options: RunOptions) -> OCRResult:
        """Detect + recognise the whole page, then drop boxes that lie mostly in ignored areas."""
        started = time.monotonic()
        self.report("ocr", None)
        boxes = self._impl.detect(image)
        mask = build_ignore_mask(image.size, regions, options.only)
        kept = [b for b in boxes if ignored_fraction(mask, b) < options.overlap_threshold]
        return OCRResult(boxes=kept, engine=self.label, elapsed=time.monotonic() - started)
