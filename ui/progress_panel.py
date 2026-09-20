"""ProgressPanel: one progress bar + a status line with an elapsed-seconds counter."""
from __future__ import annotations

import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from core.progress import ProgressUpdate


class ProgressPanel(QWidget):
    """Shows overall progress (0..1000) and what the engine is doing right now."""

    def __init__(self) -> None:
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.label = QLabel("")
        self.label.setProperty("muted", True)
        self.label.setWordWrap(True)
        v.addWidget(self.bar)
        v.addWidget(self.label)
        self._key = ""
        self._text = ""
        self._t0 = time.monotonic()
        self._running = False
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh)

    def start(self) -> None:
        """Begin a run (starts the elapsed-time counter)."""
        self._running = True
        self._key = ""
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self._timer.start()

    def on_update(self, update: ProgressUpdate) -> None:
        """Apply a :class:`ProgressUpdate` from the pipeline."""
        if update.overall is None:
            self.bar.setRange(0, 0)  # busy indicator
        else:
            if self.bar.maximum() == 0:
                self.bar.setRange(0, 1000)
            self.bar.setValue(int(max(0.0, min(1.0, update.overall)) * 1000))
        if update.key != self._key:
            self._key, self._t0 = update.key, time.monotonic()
        self._text = update.label
        self._refresh()

    def finish(self, status: str) -> None:
        """End the run; ``status`` is 'done', 'cancelled' or 'failed'."""
        self._running = False
        self._timer.stop()
        if self.bar.maximum() == 0:
            self.bar.setRange(0, 1000)
        if status == "done":
            self.bar.setValue(1000)
        self._text = {"done": "Done.", "cancelled": "Cancelled.",
                      "failed": "Failed \u2014 see the error details or the log below."}.get(status, status)
        self._refresh()

    def reset(self) -> None:
        """Clear the bar and text (e.g. when a new file is opened)."""
        self._running = False
        self._timer.stop()
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self._text = ""
        self._refresh()

    def _refresh(self) -> None:
        if self._running:
            self.label.setText(f"{self._text} \u00B7 {int(time.monotonic() - self._t0)} s")
        else:
            self.label.setText(self._text)
