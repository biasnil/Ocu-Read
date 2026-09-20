"""RegionStore: the regions drawn on the open document (per page, shared template, Only flag)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.models import KEEP, Region


class RegionStore:
    """Holds every region for one document.

    * ``per_page`` - regions in page-image pixels, by page index.
    * ``shared`` - when True every page uses ``template`` (stored as page fractions, so pages of
      different sizes still work).
    * ``only`` - document-wide switch: only Keep regions are processed.
    """

    def __init__(self) -> None:
        self.per_page: dict[int, list[Region]] = {}
        self.shared = False
        self.template: list[Region] = []  # fractional coordinates (0..1)
        self.only = False

    def get(self, page: int, size: tuple[int, int]) -> list[Region]:
        """Regions for ``page`` in the pixel coordinates of a page of ``size``."""
        w, h = size
        if self.shared:
            return [r.scaled(w, h) for r in self.template]
        return [replace(r) for r in self.per_page.get(page, [])]

    def has_keep(self, page: int) -> bool:
        """True if ``page`` has at least one Keep region."""
        regions = self.template if self.shared else self.per_page.get(page, [])
        return any(r.kind == KEEP for r in regions)

    def count(self) -> int:
        """Total number of stored regions (template counted once when shared)."""
        return len(self.template) if self.shared else sum(len(v) for v in self.per_page.values())

    def set(self, page: int, size: tuple[int, int], regions: list[Region]) -> None:
        """Replace the regions of ``page`` (or of the shared template)."""
        if self.shared:
            self.template = self._fractions(size, regions)
        else:
            self.per_page[page] = [replace(r) for r in regions]

    def enable_shared(self, page: int, size: tuple[int, int], regions: list[Region]) -> None:
        """Adopt ``regions`` of ``page`` as the template for every page."""
        self.shared = False
        self.set(page, size, regions)
        self.template = self._fractions(size, regions)
        self.shared = True

    def disable_shared(self, sizes: list[tuple[int, int]]) -> None:
        """Unlink: every page keeps the regions it was showing."""
        for i, size in enumerate(sizes):
            self.per_page[i] = self.get(i, size)
        self.shared = False

    @staticmethod
    def _fractions(size: tuple[int, int], regions: list[Region]) -> list[Region]:
        w, h = size
        return [r.normalized().scaled(1.0 / w, 1.0 / h) for r in regions]

    # ---- persistence (used by the session store) -----------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly snapshot."""
        return {
            "only": self.only,
            "shared": self.shared,
            "template": [r.to_dict() for r in self.template],
            "per_page": {str(p): [r.to_dict() for r in regs] for p, regs in self.per_page.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegionStore":
        """Inverse of :meth:`to_dict` (ignores malformed entries)."""
        store = cls()
        try:
            store.only = bool(data.get("only", False))
            store.shared = bool(data.get("shared", False))
            store.template = [Region.from_dict(d) for d in data.get("template", [])]
            store.per_page = {int(p): [Region.from_dict(d) for d in regs]
                              for p, regs in data.get("per_page", {}).items()}
        except (KeyError, TypeError, ValueError):
            return cls()
        return store
