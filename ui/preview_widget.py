"""PreviewWidget: page navigation, zoom, the region canvas and the Keep / Ignore / Only tools."""
from __future__ import annotations

from PySide6.QtGui import QResizeEvent
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSpinBox, QToolButton, QVBoxLayout,
    QWidget,
)

from core.models import IGNORE, KEEP, Region
from theme.theme_manager import ThemeManager
from ui.region_canvas import RegionCanvas


class _ZoomArea(QScrollArea):
    """Scroll area that keeps the canvas fitted to the viewport until the user zooms manually."""

    def __init__(self) -> None:
        super().__init__()
        self.canvas = RegionCanvas()
        self.setWidget(self.canvas)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fit_mode = True
        self.canvas.zoomRequested.connect(lambda d: self.zoom_by(1.25 if d > 0 else 0.8))

    def set_image(self, qimg: QImage | None) -> None:
        """Show ``qimg`` and refit."""
        self.canvas.set_image(qimg)
        self._refit()

    def zoom_by(self, factor: float) -> None:
        """Multiply the zoom by ``factor`` and stop auto-fitting."""
        self.fit_mode = False
        self.canvas.set_zoom(self.canvas.zoom * factor)

    def fit(self) -> None:
        """Fit the page to the viewport and keep fitting on resize."""
        self.fit_mode = True
        self._refit()

    def _refit(self) -> None:
        vp, c = self.viewport().size(), self.canvas
        if not c.pixmap:
            c.resize(vp)
        elif self.fit_mode:
            c.set_zoom(min((vp.width() - 4) / c.pixmap.width(), (vp.height() - 4) / c.pixmap.height(), 2.0))

    def resizeEvent(self, e: QResizeEvent) -> None:
        super().resizeEvent(e)
        self._refit()


class PreviewWidget(QWidget):
    """The left-hand side of the window.

    Signals: ``openRequested``, ``pageRequested(index)``, ``regionsChanged``, ``selectionChanged(index)``,
    ``onlyToggled(bool)``, ``applyAllToggled(bool)``.
    """

    openRequested = Signal()
    pageRequested = Signal(int)
    regionsChanged = Signal()
    selectionChanged = Signal(int)
    onlyToggled = Signal(bool)
    applyAllToggled = Signal(bool)

    def __init__(self, theme: ThemeManager) -> None:
        super().__init__()
        self._page = 0
        self._page_count = 0
        self._area = _ZoomArea()
        self.canvas = self._area.canvas
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 3, 6)

        top = QHBoxLayout()
        self.btn_open = QPushButton("Open...")
        theme.bind_icon(self.btn_open, "open")
        self.btn_open.clicked.connect(self.openRequested)
        self.btn_prev, self.btn_next = QToolButton(), QToolButton()
        self.btn_prev.setText("\u25C0")
        self.btn_next.setText("\u25B6")
        self.spin_page = QSpinBox()
        self.spin_page.setRange(1, 1)
        self.lbl_pages = QLabel("/ 0")
        self.btn_prev.clicked.connect(lambda: self.pageRequested.emit(self._page - 1))
        self.btn_next.clicked.connect(lambda: self.pageRequested.emit(self._page + 1))
        self.spin_page.valueChanged.connect(lambda val: self.pageRequested.emit(val - 1))
        self.btn_undo, self.btn_redo = QToolButton(), QToolButton()
        zoom_out, fit, zoom_in = QToolButton(), QToolButton(), QToolButton()
        for btn, icon, tip in ((self.btn_undo, "undo", "Undo region edit (Ctrl+Z)"),
                               (self.btn_redo, "redo", "Redo region edit (Ctrl+Y)"),
                               (zoom_out, "zoom_out", "Zoom out"), (fit, "fit", "Fit page"),
                               (zoom_in, "zoom_in", "Zoom in")):
            theme.bind_icon(btn, icon)
            btn.setToolTip(tip)
        self.btn_undo.clicked.connect(self.canvas.undo)
        self.btn_redo.clicked.connect(self.canvas.redo)
        zoom_out.clicked.connect(lambda: self._area.zoom_by(0.8))
        zoom_in.clicked.connect(lambda: self._area.zoom_by(1.25))
        fit.clicked.connect(self._area.fit)
        for w in (self.btn_open, self.btn_prev, self.spin_page, self.lbl_pages, self.btn_next):
            top.addWidget(w)
        top.addStretch(1)
        for w in (self.btn_undo, self.btn_redo, zoom_out, fit, zoom_in):
            top.addWidget(w)
        v.addLayout(top)
        v.addWidget(self._area, 1)

        tools = QHBoxLayout()
        tools.addWidget(QLabel("Draw as:"))
        self.btn_keep, self.btn_ignore = QPushButton("Keep"), QPushButton("Ignore")
        self.btn_keep.setObjectName("keepBtn")
        self.btn_ignore.setObjectName("ignoreBtn")
        group = QButtonGroup(self)
        for btn, kind in ((self.btn_keep, KEEP), (self.btn_ignore, IGNORE)):
            btn.setCheckable(True)
            group.addButton(btn)
            btn.clicked.connect(lambda _c=False, k=kind: setattr(self.canvas, "draw_kind", k))
        self.btn_keep.setChecked(True)
        self.btn_only = QPushButton("Only")
        self.btn_only.setObjectName("onlyBtn")
        self.btn_only.setCheckable(True)
        self.btn_only.setToolTip("When on, ONLY the Keep regions are processed; everything else is ignored.\n"
                                 "When off, unmarked areas count as Keep.")
        self.btn_only.toggled.connect(self._on_only)
        btn_del, btn_clear = QPushButton("Delete selected"), QPushButton("Clear page")
        theme.bind_icon(btn_del, "trash")
        btn_del.clicked.connect(self.canvas.delete_selected)
        btn_clear.clicked.connect(self.canvas.clear_all)
        for w in (self.btn_keep, self.btn_ignore, self.btn_only, btn_del, btn_clear):
            tools.addWidget(w)
        tools.addStretch(1)
        v.addLayout(tools)

        self.chk_all = QCheckBox("Apply these Keep/Ignore regions to all pages")
        self.chk_all.toggled.connect(self.applyAllToggled)
        v.addWidget(self.chk_all)
        hint = QLabel("Drag to draw \u00B7 click to select \u00B7 drag the selected box to move/resize \u00B7 "
                      "Ctrl+drag draws over an existing box \u00B7 K / I retag \u00B7 Del removes \u00B7 "
                      "Ctrl+Z / Ctrl+Y undo/redo \u00B7 Ctrl+wheel zooms")
        hint.setWordWrap(True)
        hint.setProperty("muted", True)
        v.addWidget(hint)

        self.canvas.regionsChanged.connect(self.regionsChanged)
        self.canvas.selectionChanged.connect(self.selectionChanged)

    # ---- API used by the main window --------------------------------------------------------
    @property
    def regions(self) -> list[Region]:
        """Regions currently on the canvas."""
        return self.canvas.regions

    def reset_zoom(self) -> None:
        """Fit the next page to the view."""
        self._area.fit_mode = True

    def set_page_count(self, count: int) -> None:
        """Update the page selector for a newly opened document."""
        self._page_count = count
        self.spin_page.blockSignals(True)
        self.spin_page.setRange(1, max(1, count))
        self.spin_page.blockSignals(False)
        self.lbl_pages.setText(f"/ {count}")

    def show_page(self, qimg: QImage, regions: list[Region], page: int) -> None:
        """Display page ``page`` with its regions."""
        self._page = page
        self._area.set_image(qimg)
        self.canvas.set_regions(regions)
        self.spin_page.blockSignals(True)
        self.spin_page.setValue(page + 1)
        self.spin_page.blockSignals(False)
        self.btn_prev.setEnabled(page > 0)
        self.btn_next.setEnabled(page < self._page_count - 1)

    def sync_page_spin(self, page: int) -> None:
        """Put the spin box back on ``page`` (after a rejected navigation request)."""
        self.spin_page.blockSignals(True)
        self.spin_page.setValue(page + 1)
        self.spin_page.blockSignals(False)

    def set_flags(self, only: bool, apply_all: bool) -> None:
        """Set the Only / Apply-to-all controls without emitting signals."""
        for widget, state in ((self.btn_only, only), (self.chk_all, apply_all)):
            widget.blockSignals(True)
            widget.setChecked(state)
            widget.blockSignals(False)
        self.canvas.set_only_mode(only)

    def _on_only(self, on: bool) -> None:
        self.canvas.set_only_mode(on)
        self.onlyToggled.emit(on)
