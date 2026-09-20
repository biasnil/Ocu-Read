"""App: the composition root. It creates every long-lived service once and hands them to the UI."""
from __future__ import annotations

import logging
import sys
from typing import Iterable

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from config.manager import ConfigManager
from core.engines import EngineFactory
from core.model_cache import ModelCache
from core.progress import TqdmBridge
from fileio.exporter import Exporter
from fileio.session_store import SessionStore
from theme.theme_manager import ThemeManager
from ui.main_window import MainWindow
from utils.logger import LogManager
from utils.paths import icon_path, logs_dir, sessions_dir

log = logging.getLogger(__name__)


class App:
    """Owns configuration, theme, logging, engine cache, sessions and the exporter.

    Nothing else in the project keeps global state; components receive what they need from here.
    """

    def __init__(self, qt_app: QApplication) -> None:
        self.qt_app = qt_app
        self.logs = LogManager(logs_dir())
        self.logs.start()
        self.config = ConfigManager()
        first_run = not self.config.existed
        self.config.load()
        if first_run:
            adopted = self.config.import_legacy(self._read_legacy_settings())
            if adopted:
                log.info("Imported %d setting(s) from the previous OCR Studio", adopted)
        log.info("OcuRead starting; config at %s", self.config.path)
        self._set_taskbar_identity()
        self.icon = QIcon(str(icon_path()))
        if self.icon.isNull():
            log.warning("Application icon not found at %s", icon_path())
        qt_app.setWindowIcon(self.icon)
        self.model_cache = ModelCache()
        self.model_cache.apply(str(self.config.get("cache_dir")))
        self.theme = ThemeManager(qt_app, self.config)
        self.theme.apply()
        self.engines = EngineFactory()
        self.sessions = SessionStore(sessions_dir())
        self.exporter = Exporter()
        self.tqdm_bridge = TqdmBridge()
        self.window: MainWindow | None = None
        qt_app.aboutToQuit.connect(self.shutdown)

    @staticmethod
    def _set_taskbar_identity() -> None:
        """On Windows, give the process its own identity so the taskbar shows OcuRead's icon, not python.exe's."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OcuRead.OcuRead")
        except Exception as ex:  # noqa: BLE001 - cosmetic only
            log.debug("Couldn't set the taskbar identity: %s", ex)

    @staticmethod
    def _read_legacy_settings() -> dict[str, object]:
        """Values saved by the old single-file app (QSettings 'OcrStudio'), if any."""
        legacy = QSettings("OcrStudio", "OcrStudio")
        return {key: legacy.value(key) for key in legacy.allKeys()}

    def create_window(self) -> MainWindow:
        """Build the main window."""
        self.window = MainWindow(self)
        return self.window

    def run(self, files: Iterable[str] = ()) -> int:
        """Show the window (opening ``files[0]`` if given) and run the Qt event loop."""
        window = self.create_window()
        window.resize(1280, 860)
        window.show()
        for path in list(files)[:1]:
            window.load_file(path)
        return self.qt_app.exec()

    def shutdown(self) -> None:
        """Flush settings and close the log file."""
        self.config.save()
        self.logs.stop()
