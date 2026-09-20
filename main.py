"""OcuRead entry point: create the Qt application and hand over to App."""
from __future__ import annotations

import multiprocessing
import os
import sys


def _ensure_std_streams() -> None:
    """A windowed (console=False) executable has no stdout/stderr; libraries that print would crash."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


def main() -> int:
    """Boot the application. All logic lives in the modules."""
    _ensure_std_streams()
    from PySide6.QtWidgets import QApplication

    from app import App

    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("OcuRead")
    return App(qt_app).run(sys.argv[1:])


if __name__ == "__main__":
    multiprocessing.freeze_support()   # required for frozen builds that spawn worker processes
    sys.exit(main())
