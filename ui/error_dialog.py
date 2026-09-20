"""Friendly error dialog with a 'Copy traceback' button."""
from __future__ import annotations

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget


def show_error(parent: QWidget | None, title: str, message: str, traceback_text: str = "") -> None:
    """Show ``message`` in a warning dialog; the traceback (if any) sits behind 'Show Details...'."""
    box = QMessageBox(QMessageBox.Icon.Warning, title, message, QMessageBox.StandardButton.Ok, parent)
    if traceback_text:
        box.setDetailedText(traceback_text)
    copy_btn = box.addButton("Copy traceback", QMessageBox.ButtonRole.ActionRole)
    box.exec()
    if box.clickedButton() is copy_btn:
        QApplication.clipboard().setText(f"{message}\n\n{traceback_text}".strip())
