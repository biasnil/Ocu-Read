"""LogPane: collapsible log viewer fed by the standard ``logging`` module."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QHBoxLayout, QPlainTextEdit, QPushButton, QToolButton, QVBoxLayout, QWidget


class _Relay(QObject):
    message = Signal(str, str)


class QtLogHandler(logging.Handler):
    """Logging handler that hands records to Qt via a signal (safe to call from any thread)."""

    def __init__(self, level: int = logging.INFO) -> None:
        super().__init__(level)
        self.relay = _Relay()

    def emit(self, record: logging.LogRecord) -> None:
        """Forward one record to the UI thread."""
        try:
            self.relay.message.emit(record.levelname, self.format(record))
        except Exception:  # noqa: BLE001 - logging must never raise
            pass


class LogPane(QWidget):
    """A 'Log' header that expands into a read-only text view with Copy / Clear buttons."""

    def __init__(self) -> None:
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        head = QHBoxLayout()
        self.toggle = QToolButton()
        self.toggle.setText("Log")
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setStyleSheet("QToolButton{border:none;font-weight:bold;background:transparent}")
        self.btn_copy, self.btn_clear = QPushButton("Copy log"), QPushButton("Clear")
        head.addWidget(self.toggle)
        head.addStretch(1)
        head.addWidget(self.btn_copy)
        head.addWidget(self.btn_clear)
        v.addLayout(head)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(3000)
        self.view.setMaximumHeight(160)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.view.setFont(mono)
        v.addWidget(self.view)
        self.btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.view.toPlainText()))
        self.btn_clear.clicked.connect(self.view.clear)
        self.toggle.toggled.connect(self._toggled)
        self.handler = QtLogHandler()
        self.handler.setFormatter(logging.Formatter("%(message)s"))
        self.handler.relay.message.connect(self.append)
        self._toggled(False)

    def attach(self) -> None:
        """Start receiving records from the root logger."""
        logging.getLogger().addHandler(self.handler)

    def detach(self) -> None:
        """Stop receiving records."""
        logging.getLogger().removeHandler(self.handler)

    def _toggled(self, on: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        for w in (self.view, self.btn_copy, self.btn_clear):
            w.setVisible(on)

    def append(self, level: str, message: str) -> None:
        """Add one line (thread-safe when reached through the handler's signal)."""
        self.view.appendPlainText(f"[{level}] {message}")

    def expand(self) -> None:
        """Open the pane."""
        self.toggle.setChecked(True)
