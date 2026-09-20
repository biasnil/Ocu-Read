"""Image preparation: region masks (Ignore / Only), rotate, deskew, binarize."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageStat

from core.models import IGNORE, KEEP, PreprocessOptions, Region, TextBox


# ---- region masks ---------------------------------------------------------------------------
def build_ignore_mask(size: tuple[int, int], regions: list[Region], only: bool = False) -> Image.Image:
    """Return an 'L' mask where 255 = ignored.

    Default: Ignore regions are 255, Keep regions are painted last so Keep wins where they overlap.
    Only mode: everything is 255 except the Keep regions (Ignore regions become redundant).
    """
    keeps = [r for r in regions if r.kind == KEEP]
    if only:
        mask = Image.new("L", size, 255)
        draw = ImageDraw.Draw(mask)
        for r in keeps:
            draw.rectangle(r.box_int(), fill=0)
        return mask
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for r in regions:
        if r.kind == IGNORE:
            draw.rectangle(r.box_int(), fill=255)
    for r in keeps:
        draw.rectangle(r.box_int(), fill=0)
    return mask


def blank_ignored(image: Image.Image, mask: Image.Image) -> Image.Image:
    """Paint the ignored area white (returns the input unchanged when nothing is ignored)."""
    if mask.getbbox() is None:
        return image
    out = image.copy()
    out.paste((255, 255, 255), (0, 0), mask)
    return out


def ignored_fraction(mask: Image.Image, box: TextBox) -> float:
    """Fraction (0..1) of ``box`` that lies inside the ignored area."""
    w, h = mask.size
    x0, y0 = max(0, int(box.x0)), max(0, int(box.y0))
    x1, y1 = min(w, int(box.x1) + 1), min(h, int(box.y1) + 1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return ImageStat.Stat(mask.crop((x0, y0, x1, y1))).mean[0] / 255.0


# ---- rotate / deskew / binarize -------------------------------------------------------------
def otsu_threshold(gray: np.ndarray) -> int:
    """Otsu's threshold for a uint8 grayscale array."""
    hist = np.bincount(gray.ravel(), minlength=256).astype(float)
    levels = np.arange(256)
    weight_bg = np.cumsum(hist)
    weight_fg = gray.size - weight_bg
    sum_bg = np.cumsum(hist * levels)
    mean_bg = sum_bg / np.where(weight_bg == 0, 1, weight_bg)
    mean_fg = (np.dot(levels, hist) - sum_bg) / np.where(weight_fg == 0, 1, weight_fg)
    between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
    between[(weight_bg == 0) | (weight_fg == 0)] = 0
    return int(np.argmax(between))


def binarize(image: Image.Image) -> Image.Image:
    """Black-and-white version of ``image`` (Otsu threshold), returned as RGB."""
    gray = np.asarray(image.convert("L"))
    thr = otsu_threshold(gray)
    return Image.fromarray(((gray > thr) * 255).astype(np.uint8)).convert("RGB")


def find_deskew_angle(image: Image.Image, max_angle: float = 10.0) -> float:
    """Angle in degrees (counter-clockwise, as PIL's ``rotate``) that straightens the text lines.

    Projection-profile search: the right angle makes text rows line up, maximising the variance of the
    row sums. Returns 0.0 for blank pages and for skew below 0.2 degrees.
    """
    gray = Image.fromarray(np.asarray(image.convert("L")))
    scale = min(1.0, 700 / max(gray.size))
    if scale < 1.0:
        gray = gray.resize((max(1, int(gray.width * scale)), max(1, int(gray.height * scale))), Image.BILINEAR)
    arr = np.asarray(gray)
    ink = Image.fromarray(((arr < otsu_threshold(arr)) * 255).astype(np.uint8))
    if ink.getbbox() is None:
        return 0.0

    def score(angle: float) -> float:
        """Row-profile variance of the ink image rotated by ``angle``."""
        rows = np.asarray(ink.rotate(angle, resample=Image.NEAREST), dtype=np.float32).sum(axis=1)
        return float(np.var(rows))

    coarse = np.arange(-max_angle, max_angle + 1e-9, 1.0)
    scores = [score(a) for a in coarse]
    if max(scores) - min(scores) < 1e-6:
        return 0.0
    best = float(coarse[int(np.argmax(scores))])
    fine = np.arange(best - 1.0, best + 1.0 + 1e-9, 0.1)
    best = float(fine[int(np.argmax([score(a) for a in fine]))])
    return round(best, 2) if abs(best) >= 0.2 else 0.0


class Preprocessor:
    """Applies the user's rotate / deskew / binarize choices to a page image."""

    _ROTATE = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}

    def __init__(self, options: PreprocessOptions | None = None) -> None:
        self.options = options or PreprocessOptions()

    @property
    def changes_geometry(self) -> bool:
        """True when output pixels no longer line up with the input (regions must be applied first)."""
        return self.options.rotate in self._ROTATE or self.options.deskew

    def apply(self, image: Image.Image) -> Image.Image:
        """Return the processed image (the input is not modified)."""
        out = image
        if self.options.rotate in self._ROTATE:
            out = out.transpose(self._ROTATE[self.options.rotate])
        if self.options.deskew:
            angle = find_deskew_angle(out)
            if angle:
                out = out.rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=(255, 255, 255))
        if self.options.binarize:
            out = binarize(out)
        return out
