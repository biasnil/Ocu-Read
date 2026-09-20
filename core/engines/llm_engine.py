"""LLM mode: Surya (local) or olmOCR / any OpenAI-compatible vision server."""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from PIL import Image

from core.devices import resolve_torch_device
from core.languages import Language
from core.models import OCRResult, Region, RunOptions, TextBox
from core.ocr_engine import OCREngine
from core.preprocessing import blank_ignored, build_ignore_mask

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ServerConfig:
    """Connection settings for an OpenAI-compatible vision endpoint (e.g. olmOCR served by vLLM)."""

    base_url: str = "http://localhost:8000/v1"
    model: str = "allenai/olmOCR-2-7B-1025"
    api_key: str = ""
    prompt: str = ""
    max_side: int = 1288


class _SuryaBackend:
    """Targets the pre-v2 Surya API (FoundationPredictor)."""

    name = "Surya"

    def __init__(self, device: str) -> None:
        self.device = device
        self._rec = None
        self._det = None

    def prepare(self) -> None:
        """Import Surya and build its predictors (downloads models on first use)."""
        dev, warn = resolve_torch_device(self.device)
        if warn:
            log.warning(warn)
        if dev:  # read by surya.settings at import time
            os.environ["TORCH_DEVICE"] = dev
        try:
            from surya.detection import DetectionPredictor
            from surya.foundation import FoundationPredictor
            from surya.recognition import RecognitionPredictor
        except ImportError as ex:
            raise RuntimeError(
                "Couldn't import the Surya 1.x API (FoundationPredictor).\n\n"
                "Surya 0.20+ (v2) replaced it with SuryaInferenceManager. Either install the last "
                'v1 release:  pip install "surya-ocr<0.20" "transformers<5.0"\n'
                "or use the 'olmOCR / OpenAI-compatible server' backend.\n\n"
                f"Import error: {ex}"
            ) from None
        self._rec = RecognitionPredictor(FoundationPredictor())
        self._det = DetectionPredictor()

    def recognize(self, image: Image.Image) -> OCRResult:
        """Detect and recognise text lines on ``image``."""
        pred = self._rec([image], det_predictor=self._det)[0]
        boxes = [TextBox(*[float(v) for v in ln.bbox], ln.text, float(getattr(ln, "confidence", 1.0) or 1.0))
                 for ln in pred.text_lines]
        return OCRResult(boxes=boxes)


class _ServerBackend:
    name = "olmOCR / vision server"

    def __init__(self, config: ServerConfig, language: Language) -> None:
        self.config = config
        self.prompt = config.prompt
        if language.hint:
            self.prompt = f"{self.prompt} The document is written in {language.hint}."

    def prepare(self) -> None:
        """Nothing to load; the server owns the model."""

    def recognize(self, image: Image.Image) -> OCRResult:
        """POST the page to the server and return its transcription."""
        cfg = self.config
        scale = cfg.max_side / max(image.size)
        if scale < 1:
            image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        payload = {
            "model": cfg.model, "temperature": 0.0, "max_tokens": 4096,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": self.prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}],
        }
        headers = {"Content-Type": "application/json"}
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"
        req = urllib.request.Request(cfg.base_url.rstrip("/") + "/chat/completions",
                                     data=json.dumps(payload).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as ex:
            raise RuntimeError(f"Server returned HTTP {ex.code}: {ex.read()[:300].decode(errors='replace')}") from None
        except urllib.error.URLError as ex:
            raise RuntimeError(f"Can't reach the vision server at {cfg.base_url}: {ex.reason}") from None
        return OCRResult(text=self.clean(data["choices"][0]["message"]["content"]))

    @staticmethod
    def clean(text: str) -> str:
        """Strip olmOCR's JSON / YAML front-matter wrappers."""
        t = text.strip()
        if t.startswith("{") and "natural_text" in t:  # olmOCR v1 JSON output
            try:
                return json.loads(t)["natural_text"].strip()
            except (ValueError, KeyError):
                pass
        m = re.match(r"---\s*\n(.*?)\n---\s*\n", t, re.S)  # olmOCR YAML front matter
        if m and "primary_language" in m.group(1):
            t = t[m.end():]
        return t.strip()


class LLMEngine(OCREngine):
    """Vision-language OCR. Ignored areas are painted white before the page reaches the model."""

    def __init__(self, backend: str = "surya", device: str = "auto", language: Language | None = None,
                 server: ServerConfig | None = None) -> None:
        super().__init__()
        self.backend_id = backend
        if backend == "server":
            self._backend = _ServerBackend(server or ServerConfig(), language or Language("Auto", None, None))
        else:
            self._backend = _SuryaBackend(device)
        self.label = self._backend.name

    def prepare(self) -> None:
        """Load the model (Surya) or do nothing (server)."""
        self._backend.prepare()

    def run(self, image: Image.Image, regions: list[Region], options: RunOptions) -> OCRResult:
        """Blank ignored areas, then transcribe the page."""
        started = time.monotonic()
        masked = blank_ignored(image, build_ignore_mask(image.size, regions, options.only))
        if self.cancelled:
            return OCRResult(text="", engine=self.label)
        self.report("model" if self.backend_id == "server" else "ocr", None)
        result = self._backend.recognize(masked)
        result.engine, result.elapsed = self.label, time.monotonic() - started
        return result
