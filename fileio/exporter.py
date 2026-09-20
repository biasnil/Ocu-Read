"""Write OCR output to disk: .txt, .md, .json, and an annotated PDF for auditing regions."""
from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path
from typing import Callable

try:
    import pymupdf as fitz
except ImportError:
    import fitz
from PIL import Image, ImageDraw

from core.models import IGNORE, KEEP, OCRResult, Region
from core.preprocessing import build_ignore_mask
from fileio.file_loader import RENDER_DPI, FileLoader


class Exporter:
    """Stateless helpers for saving results."""

    def export_text(self, path: str | Path, text: str) -> Path:
        """Write ``text`` as UTF-8 (used for both .txt and .md)."""
        p = Path(path)
        p.write_text(text, encoding="utf-8")
        return p

    def export_json(self, path: str | Path, results: list[OCRResult], source: str = "") -> Path:
        """Write per-page text and line boxes as JSON."""
        payload = {
            "source": source,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "pages": [
                {
                    "page": r.page_index + 1,
                    "engine": r.engine,
                    "text": r.text or "",
                    "boxes": [{"x0": b.x0, "y0": b.y0, "x1": b.x1, "y1": b.y1, "text": b.text,
                               "confidence": b.conf} for b in r.boxes],
                }
                for r in results
            ],
        }
        p = Path(path)
        p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return p

    def export_annotated_pdf(self, path: str | Path, loader: FileLoader,
                             regions_for_page: Callable[[int, tuple[int, int]], list[Region]],
                             only: bool = False,
                             on_page: Callable[[int, int], None] | None = None) -> Path:
        """Save a PDF of the pages with Keep regions outlined in green and ignored areas blacked out
        (dimmed when Only is on). Pages are raster images, so the file is for auditing, not for searching."""
        out = fitz.open()
        for i in range(loader.page_count):
            image = loader.render(i, cache=False).convert("RGBA")
            regions = regions_for_page(i, image.size)
            mask = build_ignore_mask(image.size, regions, only)
            shade = Image.new("RGBA", image.size, (0, 0, 0, 140 if only else 255))
            image.paste(shade, (0, 0), mask)
            draw = ImageDraw.Draw(image)
            for r in regions:
                if r.kind == KEEP:
                    draw.rectangle(r.box_int(), outline=(46, 204, 113, 255), width=4)
            buf = io.BytesIO()
            image.convert("RGB").save(buf, format="JPEG", quality=80)
            scale = 72.0 / RENDER_DPI
            page = out.new_page(width=image.width * scale, height=image.height * scale)
            page.insert_image(page.rect, stream=buf.getvalue())
            if on_page:
                on_page(i + 1, loader.page_count)
        p = Path(path)
        out.save(str(p))
        out.close()
        return p
