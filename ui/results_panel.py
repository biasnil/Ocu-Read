"""ResultsPanel: the extracted text plus Copy / Export / Clear."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget


class ResultsPanel(QWidget):
    """Editable text pane. Signal: ``exportRequested``."""

    exportRequested = Signal()
    copied = Signal()

    def __init__(self) -> None:
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 4, 0, 0)
        self.view = QPlainTextEdit()
        self.view.setPlaceholderText("Extracted text appears here...")
        self.view.setAcceptDrops(False)  # let file drops reach the main window
        self.view.viewport().setAcceptDrops(False)
        v.addWidget(self.view, 1)
        row = QHBoxLayout()
        b_copy, b_export, b_clear = QPushButton("Copy"), QPushButton("Export..."), QPushButton("Clear")
        b_copy.clicked.connect(self.copy)
        b_export.clicked.connect(self.exportRequested)
        b_clear.clicked.connect(self.view.clear)
        for b in (b_copy, b_export, b_clear):
            row.addWidget(b)
        v.addLayout(row)

    def text(self) -> str:
        """Current contents (including any edits the user made)."""
        return self.view.toPlainText()

    def clear(self) -> None:
        """Empty the pane."""
        self.view.clear()

    def append_page(self, page_index: int, text: str, heading: bool) -> None:
        """Add one page's text, optionally under a '--- Page N ---' heading."""
        chunk = text.strip()
        if heading:
            chunk = f"--- Page {page_index + 1} ---\n{chunk}"
        cur = self.view.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        cur.insertText(("\n\n" if self.view.toPlainText() else "") + chunk)
        self.view.ensureCursorVisible()

    def copy(self) -> None:
        """Copy everything to the clipboard."""
        QApplication.clipboard().setText(self.text())
        self.copied.emit()
