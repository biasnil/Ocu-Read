"""RegionListWidget: sidebar list of the regions on the current page."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from core.models import KEEP, Region
from theme.theme_manager import ThemeManager
from ui.region_canvas import COLORS


class RegionListWidget(QWidget):
    """Shows each region (colour, tag, name, size) and lets the user select, rename or delete it.

    Signals: ``selected(index)``, ``deleteRequested(index)``, ``renamed(index, name)``.
    """

    selected = Signal(int)
    deleteRequested = Signal(int)
    renamed = Signal(int, str)

    def __init__(self, theme: ThemeManager) -> None:
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 4, 0, 0)
        self.list = QListWidget()
        v.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.btn_rename, self.btn_delete = QPushButton("Rename..."), QPushButton("Delete")
        theme.bind_icon(self.btn_delete, "trash")
        row.addWidget(self.btn_rename)
        row.addWidget(self.btn_delete)
        row.addStretch(1)
        v.addLayout(row)
        self.list.currentRowChanged.connect(self._on_row)
        self.list.itemDoubleClicked.connect(lambda _i: self._rename())
        self.btn_rename.clicked.connect(self._rename)
        self.btn_delete.clicked.connect(lambda: self.deleteRequested.emit(self.list.currentRow()))
        self._update_buttons()

    def set_regions(self, regions: list[Region], selected: int = -1) -> None:
        """Rebuild the list."""
        self.list.blockSignals(True)
        self.list.clear()
        for i, r in enumerate(regions):
            n = r.normalized()
            text = f"{i + 1}. {r.kind.upper()}" + (f" \u2014 {r.name}" if r.name else "") + \
                   f"   ({int(n.x1 - n.x0)}\u00D7{int(n.y1 - n.y0)} px)"
            item = QListWidgetItem(self._swatch(r.kind), text)
            self.list.addItem(item)
        self.list.setCurrentRow(selected)
        self.list.blockSignals(False)
        self._update_buttons()

    def set_selected(self, index: int) -> None:
        """Highlight ``index`` without emitting ``selected``."""
        self.list.blockSignals(True)
        self.list.setCurrentRow(index)
        self.list.blockSignals(False)
        self._update_buttons()

    @staticmethod
    def _swatch(kind: str) -> QIcon:
        pm = QPixmap(14, 14)
        pm.fill(COLORS.get(kind, COLORS[KEEP]))
        return QIcon(pm)

    def _on_row(self, row: int) -> None:
        self._update_buttons()
        self.selected.emit(row)

    def _update_buttons(self) -> None:
        has = self.list.currentRow() >= 0
        self.btn_rename.setEnabled(has)
        self.btn_delete.setEnabled(has)

    def _rename(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        name, ok = QInputDialog.getText(self, "Rename region", "Name:", text="")
        if ok:
            self.renamed.emit(row, name.strip())
