"""Filesystem locations used by OcuRead (config, sessions, logs, cache, bundled assets)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "OcuRead"


def appdata_dir() -> Path:
    """Per-user data root, created on demand.

    Windows: %APPDATA%\\OcuRead   macOS: ~/Library/Application Support/OcuRead
    Linux: $XDG_CONFIG_HOME or ~/.config/OcuRead.  Set OCUREAD_HOME to override (handy for tests).
    """
    override = os.environ.get("OCUREAD_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def _subdir(name: str) -> Path:
    path = appdata_dir() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    """Location of config.json."""
    return appdata_dir() / "config.json"


def sessions_dir() -> Path:
    """Folder with one saved region-set per opened file."""
    return _subdir("sessions")


def logs_dir() -> Path:
    """Folder with rolling log files."""
    return _subdir("logs")


def cache_dir() -> Path:
    """Scratch folder owned by OcuRead (models stay in each library's own cache unless configured)."""
    return _subdir("cache")


def project_root() -> Path:
    """Folder that contains main.py - or, in a PyInstaller build, the folder holding the bundled data files."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def icon_path() -> Path:
    """Application icon (PNG works on every platform; icon.ico is used for the Windows exe)."""
    return project_root() / "assets" / "icon.png"


def icons_dir() -> Path:
    """Bundled SVG icons."""
    return project_root() / "assets" / "icons"


def theme_dir() -> Path:
    """Folder with the .qss stylesheets."""
    return project_root() / "theme"
