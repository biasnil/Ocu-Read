"""Stage-weighted progress reporting, and a bridge that turns tqdm bars into progress events."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator

# stage -> (start, end, label): each page owns an equal slice of the overall bar and this splits the slice.
STAGES: dict[str, tuple[float, float, str]] = {
    "detect": (0.00, 0.20, "Detecting layout"),
    "recognize": (0.20, 0.90, "Recognizing text"),
    "ocr": (0.00, 0.90, "Detecting + recognizing text"),   # engines that can't split the two
    "model": (0.00, 0.90, "Waiting for the model"),
    "assemble": (0.90, 1.00, "Assembling output"),
}


@dataclass
class ProgressUpdate:
    """One progress event.

    phase: "loading" (models), "page" (OCR) or "done".
    overall: 0..1 for the whole run, or None when unknown (busy indicator).
    label: human-readable text; key: changes when the stage changes (used to reset the elapsed timer).
    """

    phase: str
    overall: float | None
    label: str
    key: str


ProgressListener = Callable[[ProgressUpdate], None]
StageReporter = Callable[[str, "float | None"], None]


def noop_stage(stage: str, frac: float | None = None) -> None:
    """Default stage reporter that ignores everything."""


class ProgressTracker:
    """Converts engine stage reports and tqdm events into :class:`ProgressUpdate` events."""

    def __init__(self, total_pages: int, listener: ProgressListener) -> None:
        self._total = max(1, total_pages)
        self._listener = listener
        self._cur = 0
        self._loading = True

    def loading(self, label: str, frac: float | None = None) -> None:
        """Report model loading / downloading."""
        self._loading = True
        text = label if frac is None else f"{label} {int(frac * 100)}%"
        self._listener(ProgressUpdate("loading", frac, text, "load"))

    def begin_page(self, index_in_run: int) -> None:
        """Start page number ``index_in_run`` (0-based within this run)."""
        self._loading = False
        self._cur = index_in_run

    def report(self, stage: str, frac: float | None = None) -> None:
        """Report progress inside the current page's ``stage``."""
        lo, hi, label = STAGES[stage]
        f = None if frac is None else max(0.0, min(1.0, frac))
        overall = (self._cur + lo + (hi - lo) * (f or 0.0)) / self._total
        text = f"Page {self._cur + 1} / {self._total} \u2014 {label}\u2026"
        if f is not None:
            text += f" {int(f * 100)}%"
        self._listener(ProgressUpdate("page", overall, text, f"{self._cur}:{stage}"))

    def page_done(self) -> None:
        """Mark the current page finished."""
        n = self._cur + 1
        self._listener(ProgressUpdate("page", n / self._total, f"Page {n} / {self._total} \u2014 done", f"{self._cur}:done"))

    def on_tqdm(self, bar: Any, event: str) -> None:
        """Handle a tqdm bar event ('open' | 'update' | 'close')."""
        desc = (getattr(bar, "desc", "") or "").strip()
        total = getattr(bar, "total", None)
        frac = (bar.n / total) if total else None
        if event == "close" and total:
            frac = 1.0
        if self._loading:
            self.loading(f"Loading models \u2014 {desc or 'files'}", frac)
            return
        low = desc.lower()
        if "detect" in low:
            self.report("detect", frac)
        elif "recogni" in low:
            self.report("recognize", frac)


class _NullFile:
    def write(self, _s: str) -> int:
        """Swallow output."""
        return 0

    def flush(self) -> None:
        """No-op."""


class TqdmBridge:
    """Silences tqdm's console output and forwards bar events to a callback while attached.

    Patching tqdm is process-wide by nature (libraries create their own bars), so the active callback is
    stored on the tqdm class itself; outside :meth:`attached`, tqdm behaves exactly as before.
    """

    _ATTR = "_ocuread_callback"

    @contextmanager
    def attached(self, callback: Callable[[Any, str], None]) -> Iterator[None]:
        """While active, tqdm bars call ``callback(bar, event)`` instead of drawing on the console."""
        std = self._install()
        if std is not None:
            setattr(std.tqdm, self._ATTR, callback)
        try:
            yield
        finally:
            if std is not None:
                setattr(std.tqdm, self._ATTR, None)

    def _install(self) -> Any:
        try:
            import tqdm.std as std
        except ImportError:
            return None
        cls = std.tqdm
        if getattr(cls, "_ocuread_patched", False):
            return std
        attr = self._ATTR
        orig_init, orig_display, orig_close = cls.__init__, cls.display, cls.close

        def fire(bar: Any, event: str) -> None:
            """Call the active callback, never raising into tqdm."""
            cb = getattr(cls, attr, None)
            if cb is not None:
                try:
                    cb(bar, event)
                except Exception:
                    pass

        def init(self: Any, *a: Any, **k: Any) -> None:
            """Patched tqdm.__init__: silence the bar and announce it."""
            orig_init(self, *a, **k)
            if getattr(cls, attr, None) is not None and not getattr(self, "disable", False):
                self.fp = _NullFile()
                fire(self, "open")

        def display(self: Any, msg: Any = None, pos: Any = None) -> Any:
            """Patched tqdm.display: report instead of drawing."""
            if getattr(cls, attr, None) is None:
                return orig_display(self, msg, pos)
            fire(self, "update")

        def close(self: Any) -> None:
            """Patched tqdm.close: report completion."""
            was_open = not getattr(self, "disable", False)
            orig_close(self)
            if was_open:
                fire(self, "close")

        cls.__init__, cls.display, cls.close = init, display, close
        cls._ocuread_patched = True
        return std
