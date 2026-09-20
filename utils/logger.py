"""Logging setup: a rolling file in %APPDATA%\\OcuRead\\logs plus helpers for the rest of the app."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


class LogManager:
    """Owns the rotating file handler attached to the root logger.

    Every module logs through the standard ``logging`` package (``logging.getLogger(__name__)``);
    the UI log pane attaches its own handler to the same root logger, so nothing is printed to the console.
    """

    FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

    def __init__(self, log_dir: Path, level: int = logging.INFO) -> None:
        self._log_dir = log_dir
        self._level = level
        self._handler: RotatingFileHandler | None = None

    @property
    def log_file(self) -> Path:
        """Path of the current log file."""
        return self._log_dir / "ocuread.log"

    def start(self) -> None:
        """Attach the file handler (idempotent)."""
        if self._handler is not None:
            return
        self._log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(self.log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter(self.FORMAT))
        handler.setLevel(self._level)
        root = logging.getLogger()
        root.addHandler(handler)
        root.setLevel(self._level)
        self._handler = handler

    def stop(self) -> None:
        """Detach and close the file handler."""
        if self._handler is not None:
            logging.getLogger().removeHandler(self._handler)
            self._handler.close()
            self._handler = None
