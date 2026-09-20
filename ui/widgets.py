"""Small Qt helpers shared by several panels."""
from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtWidgets import QComboBox


def make_combo(items: Sequence[tuple[str, Any]]) -> QComboBox:
    """Combo box whose entries are (label, stored value) pairs."""
    combo = QComboBox()
    for label, data in items:
        combo.addItem(label, data)
    return combo


def set_combo(combo: QComboBox, data: Any) -> None:
    """Select the entry whose stored value is ``data`` (first entry if it isn't found)."""
    i = combo.findData(data)
    combo.setCurrentIndex(i if i >= 0 else 0)
