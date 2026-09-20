"""ThemeManager: applies the dark / light stylesheet, tints icons to match, and remembers the choice."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QByteArray, QObject, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QWidget

from config.manager import ConfigManager
from utils.paths import icons_dir, theme_dir

log = logging.getLogger(__name__)

ICON_COLORS = {"dark": "#d4d4d4", "light": "#2b2b2b"}
# Mirrors the colours in the .qss files so widgets that paint themselves (the region canvas) match.
PALETTES = {
    "dark": {"window": "#1e1f22", "base": "#26282b", "alt": "#2b2d30", "text": "#dfe1e5", "muted": "#8a8f98", "highlight": "#3d7fe0"},
    "light": {"window": "#f3f4f6", "base": "#ffffff", "alt": "#eceef1", "text": "#1f2328", "muted": "#6b7280", "highlight": "#2563eb"},
}


class ThemeManager(QObject):
    """Owns the application's look. ``changed(name)`` fires after a new theme has been applied."""

    changed = Signal(str)

    def __init__(self, app: QApplication, config: ConfigManager) -> None:
        super().__init__()
        self._app = app
        self._config = config
        self._bound: list[tuple[QWidget, str]] = []
        self._icon_cache: dict[tuple[str, str], QIcon] = {}

    @property
    def current(self) -> str:
        """Name of the active theme ('dark' or 'light')."""
        name = str(self._config.get("theme"))
        return name if (theme_dir() / f"{name}.qss").exists() else "dark"

    def apply(self) -> None:
        """Apply the theme named in the config (Fusion style + the .qss file) and refresh bound icons."""
        name = self.current
        self._app.setStyle("Fusion")
        self._app.setPalette(self._palette(name))
        qss = (theme_dir() / f"{name}.qss").read_text(encoding="utf-8").replace("__ICONS__", icons_dir().as_posix())
        self._app.setStyleSheet(qss)
        self._refresh_icons()
        log.info("Theme applied: %s", name)
        self.changed.emit(name)

    @staticmethod
    def _palette(name: str) -> QPalette:
        c = PALETTES[name]
        pal = QPalette()
        R, G = QPalette.ColorRole, QPalette.ColorGroup
        for role, key in ((R.Window, "window"), (R.WindowText, "text"), (R.Base, "base"), (R.AlternateBase, "alt"),
                          (R.Text, "text"), (R.Button, "alt"), (R.ButtonText, "text"), (R.ToolTipBase, "alt"),
                          (R.ToolTipText, "text"), (R.Highlight, "highlight"), (R.PlaceholderText, "muted"),
                          (R.Mid, "muted")):
            pal.setColor(role, QColor(c[key]))
        pal.setColor(R.HighlightedText, QColor("#ffffff"))
        for role in (R.Text, R.ButtonText, R.WindowText):
            pal.setColor(G.Disabled, role, QColor(c["muted"]))
        return pal

    def set_theme(self, name: str) -> None:
        """Switch theme, persist it and apply it."""
        self._config.update({"theme": name})
        self.apply()

    def toggle(self) -> None:
        """Flip between dark and light."""
        self.set_theme("light" if self.current == "dark" else "dark")

    def icon(self, name: str) -> QIcon:
        """Icon from assets/icons tinted for the current theme (empty icon if the file is missing)."""
        key = (name, self.current)
        if key in self._icon_cache:
            return self._icon_cache[key]
        path: Path = icons_dir() / f"{name}.svg"
        icon = QIcon()
        if path.exists():
            svg = path.read_text(encoding="utf-8").replace("currentColor", ICON_COLORS[self.current])
            renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
            pm = QPixmap(48, 48)
            pm.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pm)
            renderer.render(painter)
            painter.end()
            pm.setDevicePixelRatio(2.0)
            icon = QIcon(pm)
        self._icon_cache[key] = icon
        return icon

    def bind_icon(self, widget: QWidget, name: str) -> None:
        """Give ``widget`` (a button) the icon ``name`` now and re-tint it whenever the theme changes."""
        self._bound = [(w, n) for w, n in self._bound if w is not widget]
        self._bound.append((widget, name))
        widget.setIcon(self.icon(name))  # type: ignore[attr-defined]

    def _refresh_icons(self) -> None:
        alive: list[tuple[QWidget, str]] = []
        for widget, name in self._bound:
            try:
                widget.setIcon(self.icon(name))  # type: ignore[attr-defined]
                alive.append((widget, name))
            except RuntimeError:  # the C++ widget was deleted
                pass
        self._bound = alive
