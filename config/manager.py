"""ConfigManager: load / validate / migrate / save the user's settings as JSON."""
from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Mapping

from config.defaults import CONFIG_VERSION, DEFAULTS
from utils.paths import config_path

log = logging.getLogger(__name__)

# version N -> function that upgrades a settings dict from N to N+1
_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


class ConfigManager:
    """Typed access to settings stored in ``config.json`` under the app-data folder.

    * Unknown keys in the file are dropped, missing keys fall back to ``DEFAULTS`` (defaults-merge).
    * Values are coerced to the type of their default; bad values fall back to the default.
    * A corrupt file is moved aside to ``config.json.bad`` and defaults are used.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or config_path()
        self._data: dict[str, Any] = dict(DEFAULTS)
        self.existed = self._path.exists()

    @property
    def path(self) -> Path:
        """Location of the JSON file."""
        return self._path

    # ---- reading / writing values -------------------------------------------------------
    def get(self, key: str) -> Any:
        """Return the current value of ``key`` (KeyError for unknown keys)."""
        return self._data[key]

    def set(self, key: str, value: Any) -> None:
        """Change a value in memory (call :meth:`save` to persist)."""
        if key not in DEFAULTS:
            raise KeyError(key)
        self._data[key] = self._coerce(key, value)

    def update(self, values: Mapping[str, Any]) -> None:
        """Set several values and save once."""
        for key, value in values.items():
            self.set(key, value)
        self.save()

    def reset(self) -> None:
        """Restore every setting to its default and save."""
        self._data = dict(DEFAULTS)
        self.save()

    # ---- persistence ---------------------------------------------------------------------
    def load(self) -> None:
        """Read the file (if any), migrate it, merge it over the defaults."""
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("config root must be an object")
        except (OSError, ValueError) as ex:
            bad = self._path.with_suffix(".json.bad")
            log.warning("Config unreadable (%s); moved to %s and using defaults", ex, bad.name)
            try:
                shutil.move(str(self._path), str(bad))
            except OSError:
                pass
            return
        self._data = self._merge(self.migrate(raw))

    def save(self) -> None:
        """Write the file atomically (temp file + rename)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": CONFIG_VERSION, **self._data}
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self._path)

    def import_legacy(self, legacy: Mapping[str, Any]) -> int:
        """Adopt settings from the old single-file app (keys like ``llm/base_url``). Returns how many were used."""
        used = 0
        for old_key, value in legacy.items():
            key = old_key.replace("/", "_")
            if key in DEFAULTS:
                self._data[key] = self._coerce(key, value)
                used += 1
        if used:
            self.save()
        return used

    @staticmethod
    def migrate(data: dict[str, Any]) -> dict[str, Any]:
        """Upgrade an older settings dict to the current version."""
        version = int(data.get("version", 0) or 0)
        while version < CONFIG_VERSION:
            step = _MIGRATIONS.get(version)
            if step:
                data = step(data)
            version += 1
        data["version"] = CONFIG_VERSION
        return data

    # ---- helpers -------------------------------------------------------------------------
    def _merge(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        merged = dict(DEFAULTS)
        for key in DEFAULTS:
            if key in raw:
                merged[key] = self._coerce(key, raw[key])
        return merged

    @staticmethod
    def _coerce(key: str, value: Any) -> Any:
        default = DEFAULTS[key]
        try:
            if isinstance(default, bool):
                return value in (True, "true", "True", 1, "1")
            return type(default)(value)
        except (TypeError, ValueError):
            return default
