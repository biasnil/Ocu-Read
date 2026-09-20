"""Plain data types shared by the core, the file layer and the UI (no Qt, no I/O)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any

KEEP = "keep"
IGNORE = "ignore"


@dataclass
class Region:
    """A rectangle in page-image pixel coordinates, tagged Keep or Ignore (optionally named)."""

    x0: float
    y0: float
    x1: float
    y1: float
    kind: str = KEEP
    name: str = ""

    def normalized(self) -> "Region":
        """Copy with x0<=x1 and y0<=y1."""
        return replace(self, x0=min(self.x0, self.x1), y0=min(self.y0, self.y1),
                       x1=max(self.x0, self.x1), y1=max(self.y0, self.y1))

    def box_int(self) -> tuple[int, int, int, int]:
        """Rounded (x0, y0, x1, y1) suitable for PIL drawing."""
        r = self.normalized()
        return int(round(r.x0)), int(round(r.y0)), int(round(r.x1)), int(round(r.y1))

    def scaled(self, sx: float, sy: float) -> "Region":
        """Copy with coordinates multiplied by (sx, sy)."""
        return replace(self, x0=self.x0 * sx, y0=self.y0 * sy, x1=self.x1 * sx, y1=self.y1 * sy)

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly form."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Region":
        """Inverse of :meth:`to_dict`; tolerant of missing optional fields."""
        kind = data.get("kind", KEEP)
        return cls(float(data["x0"]), float(data["y0"]), float(data["x1"]), float(data["y1"]),
                   kind if kind in (KEEP, IGNORE) else KEEP, str(data.get("name", "")))


@dataclass
class TextBox:
    """One recognised line of text with its bounding box (page-image pixels)."""

    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    conf: float = 1.0


@dataclass
class OCRResult:
    """Result for one page. Engines that return boxes leave ``text`` as None; the post-processor fills it."""

    page_index: int = 0
    text: str | None = None
    boxes: list[TextBox] = field(default_factory=list)
    engine: str = ""
    elapsed: float = 0.0


@dataclass
class PageJob:
    """One page to process, with the regions that apply to it."""

    page_index: int
    regions: list[Region] = field(default_factory=list)


@dataclass
class RunOptions:
    """Options for one OCR run."""

    overlap_threshold: float = 0.5   # Normal mode: drop a box when this much of it is ignored
    min_confidence: float = 0.0      # drop boxes below this confidence
    dehyphenate: bool = False
    normalize_whitespace: bool = False
    only: bool = False               # True: only Keep regions are processed


@dataclass
class PreprocessOptions:
    """Image clean-up applied before OCR."""

    rotate: int = 0        # clockwise degrees: 0, 90, 180, 270
    deskew: bool = False
    binarize: bool = False
