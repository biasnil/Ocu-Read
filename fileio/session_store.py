"""Save and restore the regions drawn on a file, so re-opening it later picks up where you left off."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class SessionStore:
    """One small JSON file per source file, kept in the sessions folder.

    The store deals in plain dicts (produced/consumed by the UI's region model), so it has no UI dependency.
    A session is only restored if the file's size and page count still match what was saved.
    """

    def __init__(self, sessions_dir: Path) -> None:
        self._dir = sessions_dir

    def _file_for(self, source: str | Path) -> Path:
        src = Path(source)
        digest = hashlib.sha1(str(src.resolve()).encode("utf-8")).hexdigest()[:12]
        return self._dir / f"{src.stem[:40]}-{digest}.json"

    @staticmethod
    def _fingerprint(source: str | Path) -> int:
        try:
            return Path(source).stat().st_size
        except OSError:
            return -1

    def save(self, source: str | Path, page_count: int, data: dict[str, Any]) -> None:
        """Store ``data`` for ``source``."""
        self._dir.mkdir(parents=True, exist_ok=True)
        payload = {"source": str(source), "size": self._fingerprint(source), "page_count": page_count, "regions": data}
        self._file_for(source).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load(self, source: str | Path, page_count: int) -> dict[str, Any] | None:
        """Return the saved data for ``source`` if it still matches the file, else None."""
        f = self._file_for(source)
        if not f.exists():
            return None
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as ex:
            log.warning("Ignoring unreadable session file %s: %s", f.name, ex)
            return None
        if payload.get("size") != self._fingerprint(source) or payload.get("page_count") != page_count:
            return None
        return payload.get("regions")

    def delete(self, source: str | Path) -> None:
        """Remove the saved session for ``source`` (if any)."""
        self._file_for(source).unlink(missing_ok=True)
