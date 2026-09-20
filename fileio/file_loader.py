"""Load PDFs and images and render their pages to PIL images."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

try:
    import pymupdf as fitz  # PyMuPDF >= 1.24.3
except ImportError:  # older installs
    import fitz
from PIL import Image, ImageOps

RENDER_DPI = 200
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
SUPPORTED_EXTS = IMAGE_EXTS | {".pdf"}


def flatten_to_rgb(img: Image.Image) -> Image.Image:
    """RGB copy of ``img``; transparent areas become white."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(bg, rgba).convert("RGB")
    return img.convert("RGB")


class FileLoader:
    """One opened PDF or image. PDF pages are rendered at ``RENDER_DPI`` so region coordinates are stable.

    Not thread-safe: open a separate ``FileLoader`` per thread.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self.is_pdf = Path(path).suffix.lower() == ".pdf"
        self._cache: OrderedDict[int, Image.Image] = OrderedDict()
        if self.is_pdf:
            self._pdf = fitz.open(self.path)
            if self._pdf.needs_pass:
                raise ValueError("Password-protected PDFs are not supported.")
            if self._pdf.page_count == 0:
                raise ValueError("This PDF has no pages.")
            self.page_count = self._pdf.page_count
        else:
            self._img = Image.open(self.path)
            self.page_count = getattr(self._img, "n_frames", 1)

    def __enter__(self) -> "FileLoader":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _matrix(self) -> "fitz.Matrix":
        s = RENDER_DPI / 72.0
        return fitz.Matrix(s, s)

    def page_size(self, index: int) -> tuple[int, int]:
        """(width, height) in pixels of page ``index`` as rendered by :meth:`render`."""
        if self.is_pdf:
            r = (self._pdf[index].rect * self._matrix()).irect
            return r.width, r.height
        return self.render(index).size

    def render(self, index: int, cache: bool = True) -> Image.Image:
        """Page ``index`` as an RGB image (the last few pages are cached when ``cache`` is true)."""
        if cache and index in self._cache:
            self._cache.move_to_end(index)
            return self._cache[index]
        if self.is_pdf:
            pix = self._pdf[index].get_pixmap(matrix=self._matrix(), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        else:
            self._img.seek(index)
            img = flatten_to_rgb(ImageOps.exif_transpose(self._img))
        if cache:
            self._cache[index] = img
            while len(self._cache) > 4:
                self._cache.popitem(last=False)
        return img

    def close(self) -> None:
        """Release the file handle."""
        try:
            (self._pdf if self.is_pdf else self._img).close()
        except Exception:  # noqa: BLE001
            pass
