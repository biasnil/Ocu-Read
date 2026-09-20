"""RegionCanvas: shows a page image and lets the user draw, select, move, resize and edit regions."""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtGui import QContextMenuEvent, QKeyEvent, QMouseEvent, QPaintEvent, QWheelEvent
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor, QCursor, QFont, QFontMetrics, QImage, QKeySequence, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import QMenu, QWidget

from core.models import IGNORE, KEEP, Region

COLORS = {KEEP: QColor(46, 204, 113), IGNORE: QColor(231, 76, 60)}


class RegionCanvas(QWidget):
    """Interactive page view. Coordinates stored in :attr:`regions` are page-image pixels.

    Signals: ``regionsChanged`` after any edit, ``selectionChanged(index)`` (-1 = none),
    ``zoomRequested(+1/-1)`` for Ctrl+wheel.
    """

    regionsChanged = Signal()
    selectionChanged = Signal(int)
    zoomRequested = Signal(int)
    HANDLE = 7
    MIN_SIZE = 6  # widget pixels

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.pixmap: QPixmap | None = None
        self.zoom = 1.0
        self.regions: list[Region] = []
        self.sel = -1
        self.draw_kind = KEEP
        self.only_mode = False
        self._drag: dict | None = None
        self._undo: list[list[Region]] = []
        self._redo: list[list[Region]] = []

    # ---- public API ---------------------------------------------------------------------
    def set_image(self, qimg: QImage | None) -> None:
        """Show a new page image (clears selection and undo history)."""
        self.pixmap = QPixmap.fromImage(qimg) if qimg is not None else None
        self._drag = None
        self._undo.clear()
        self._redo.clear()
        self._set_sel(-1)
        self._apply_size()

    def set_regions(self, regions: list[Region]) -> None:
        """Replace the regions shown (clears selection and undo history)."""
        self.regions = [r.normalized() for r in regions]
        self._undo.clear()
        self._redo.clear()
        self._set_sel(-1)
        self.update()

    def set_only_mode(self, on: bool) -> None:
        """Dim everything outside the Keep regions while Only is on."""
        self.only_mode = on
        self.update()

    def set_zoom(self, z: float) -> None:
        """Set the zoom factor (0.05 .. 8)."""
        self.zoom = max(0.05, min(z, 8.0))
        self._apply_size()

    def select(self, index: int) -> None:
        """Select region ``index`` (-1 clears the selection)."""
        self._set_sel(index if 0 <= index < len(self.regions) else -1)
        self.update()

    def undo(self) -> None:
        """Undo the last region edit."""
        if self._undo:
            self._redo.append(self._snap())
            self.regions = self._undo.pop()
            self._set_sel(-1)
            self.update()
            self.regionsChanged.emit()

    def redo(self) -> None:
        """Redo the last undone edit."""
        if self._redo:
            self._undo.append(self._snap())
            self.regions = self._redo.pop()
            self._set_sel(-1)
            self.update()
            self.regionsChanged.emit()

    def delete_selected(self) -> None:
        """Delete the selected region."""
        if 0 <= self.sel < len(self.regions):
            self._push_undo()
            del self.regions[self.sel]
            self._set_sel(-1)
            self.update()
            self.regionsChanged.emit()

    def set_selected_kind(self, kind: str) -> None:
        """Retag the selected region as Keep or Ignore."""
        if 0 <= self.sel < len(self.regions) and self.regions[self.sel].kind != kind:
            self._push_undo()
            self.regions[self.sel].kind = kind
            self.update()
            self.regionsChanged.emit()

    def rename_region(self, index: int, name: str) -> None:
        """Give region ``index`` a display name."""
        if 0 <= index < len(self.regions) and self.regions[index].name != name:
            self._push_undo()
            self.regions[index].name = name
            self.update()
            self.regionsChanged.emit()

    def clear_all(self) -> None:
        """Remove every region on this page."""
        if self.regions:
            self._push_undo()
            self.regions = []
            self._set_sel(-1)
            self.update()
            self.regionsChanged.emit()

    # ---- internals ----------------------------------------------------------------------
    def _set_sel(self, index: int) -> None:
        if index != self.sel:
            self.sel = index
            self.selectionChanged.emit(index)

    def _snap(self) -> list[Region]:
        return [replace(r) for r in self.regions]

    def _push_undo(self, snap: list[Region] | None = None) -> None:
        self._undo.append(snap if snap is not None else self._snap())
        del self._undo[:-100]
        self._redo.clear()

    def _apply_size(self) -> None:
        if self.pixmap:
            self.resize(round(self.pixmap.width() * self.zoom), round(self.pixmap.height() * self.zoom))
        self.update()

    def _to_img(self, p: QPointF) -> QPointF:
        x = min(max(p.x() / self.zoom, 0.0), float(self.pixmap.width()))
        y = min(max(p.y() / self.zoom, 0.0), float(self.pixmap.height()))
        return QPointF(x, y)

    def _rect_w(self, r: Region) -> QRectF:
        z = self.zoom
        return QRectF(r.x0 * z, r.y0 * z, (r.x1 - r.x0) * z, (r.y1 - r.y0) * z).normalized()

    def _region_at(self, pos: QPointF) -> int:
        for i in range(len(self.regions) - 1, -1, -1):
            if self._rect_w(self.regions[i]).contains(pos):
                return i
        return -1

    def _hit(self, pos: QPointF) -> tuple[int, str]:
        """(index, mode) where mode is 'move' or a resize handle: tl tr bl br l r t b."""
        m = self.HANDLE
        order = ([self.sel] if self.sel >= 0 else []) + \
                [i for i in range(len(self.regions) - 1, -1, -1) if i != self.sel]
        for i in order:
            rect = self._rect_w(self.regions[i])
            if not rect.adjusted(-m, -m, m, m).contains(pos):
                continue
            mode = ""
            if abs(pos.y() - rect.top()) <= m:
                mode += "t"
            elif abs(pos.y() - rect.bottom()) <= m:
                mode += "b"
            if abs(pos.x() - rect.left()) <= m:
                mode += "l"
            elif abs(pos.x() - rect.right()) <= m:
                mode += "r"
            if mode:
                return i, mode
            if rect.contains(pos):
                return i, "move"
        return -1, ""

    # ---- mouse / keyboard ---------------------------------------------------------------
    def mousePressEvent(self, e: QMouseEvent) -> None:
        if not self.pixmap or e.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus()
        pos = e.position()
        ctrl = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        idx, mode = (-1, "") if ctrl else self._hit(pos)
        if idx >= 0 and idx == self.sel and mode:
            self._drag = {"mode": mode, "idx": idx, "start_w": pos, "orig": replace(self.regions[idx]),
                          "snap": self._snap()}
        else:  # drag draws a new region; a plain click selects (handled on release)
            self._drag = {"mode": "new", "start_w": pos, "start": self._to_img(pos), "region": None}

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if not self.pixmap:
            return
        pos, d = e.position(), self._drag
        if d is None:
            self._update_cursor(pos)
            return
        ip = self._to_img(pos)
        if d["mode"] == "new":
            if d["region"] is None and (pos - d["start_w"]).manhattanLength() < 4:
                return
            s = d["start"]
            d["region"] = Region(s.x(), s.y(), ip.x(), ip.y(), self.draw_kind)
        else:
            r, o = self.regions[d["idx"]], d["orig"]
            if d["mode"] == "move":
                delta = (pos - d["start_w"]) / self.zoom
                w, h = o.x1 - o.x0, o.y1 - o.y0
                r.x0 = min(max(o.x0 + delta.x(), 0.0), self.pixmap.width() - w)
                r.y0 = min(max(o.y0 + delta.y(), 0.0), self.pixmap.height() - h)
                r.x1, r.y1 = r.x0 + w, r.y0 + h
            else:
                if "l" in d["mode"]:
                    r.x0 = ip.x()
                if "r" in d["mode"]:
                    r.x1 = ip.x()
                if "t" in d["mode"]:
                    r.y0 = ip.y()
                if "b" in d["mode"]:
                    r.y1 = ip.y()
        self.update()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        d, self._drag = self._drag, None
        if d is None or e.button() != Qt.MouseButton.LeftButton:
            return
        if d["mode"] == "new":
            reg = d["region"]
            if reg is None:  # click -> select topmost region under the cursor
                self._set_sel(self._region_at(e.position()))
            else:
                reg = reg.normalized()
                if (reg.x1 - reg.x0) * self.zoom >= self.MIN_SIZE and (reg.y1 - reg.y0) * self.zoom >= self.MIN_SIZE:
                    self._push_undo()
                    self.regions.append(reg)
                    self._set_sel(len(self.regions) - 1)
                    self.regionsChanged.emit()
        else:
            self.regions[d["idx"]] = self.regions[d["idx"]].normalized()
            if d["snap"] != self._snap():  # only record real edits
                self._push_undo(d["snap"])
                self.regionsChanged.emit()
        self.update()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        k = e.key()
        if e.matches(QKeySequence.StandardKey.Undo):
            self.undo()
        elif e.matches(QKeySequence.StandardKey.Redo):
            self.redo()
        elif k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
        elif k == Qt.Key.Key_Escape:
            self._set_sel(-1)
            self.update()
        elif k == Qt.Key.Key_K:
            self.set_selected_kind(KEEP)
        elif k == Qt.Key.Key_I:
            self.set_selected_kind(IGNORE)
        else:
            super().keyPressEvent(e)

    def wheelEvent(self, e: QWheelEvent) -> None:
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoomRequested.emit(1 if e.angleDelta().y() > 0 else -1)
            e.accept()
        else:
            e.ignore()

    def contextMenuEvent(self, e: QContextMenuEvent) -> None:
        if not self.pixmap:
            return
        idx = self._region_at(QPointF(e.pos()))
        if idx < 0:
            return
        self._set_sel(idx)
        self.update()
        menu = QMenu(self)
        a_keep = menu.addAction("Mark as Keep  (K)")
        a_ign = menu.addAction("Mark as Ignore  (I)")
        menu.addSeparator()
        a_del = menu.addAction("Delete region  (Del)")
        chosen = menu.exec(e.globalPos())
        if chosen is a_keep:
            self.set_selected_kind(KEEP)
        elif chosen is a_ign:
            self.set_selected_kind(IGNORE)
        elif chosen is a_del:
            self.delete_selected()

    def _update_cursor(self, pos: QPointF) -> None:
        idx, mode = self._hit(pos)
        shape = Qt.CursorShape.CrossCursor
        if idx >= 0 and idx == self.sel:
            shape = {
                "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
                "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
                "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
                "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
                "move": Qt.CursorShape.SizeAllCursor,
            }.get(mode, shape)
        self.setCursor(QCursor(shape))

    # ---- painting -----------------------------------------------------------------------
    def paintEvent(self, _e: QPaintEvent) -> None:
        p = QPainter(self)
        if not self.pixmap:
            p.fillRect(self.rect(), self.palette().alternateBase())
            p.setPen(QPen(self.palette().mid().color(), 2, Qt.PenStyle.DashLine))
            p.drawRoundedRect(self.rect().adjusted(24, 24, -24, -24), 12, 12)
            p.setPen(self.palette().text().color())
            f = QFont(self.font())
            f.setPointSize(f.pointSize() + 3)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Drop a PDF or image here\nor click  Open...")
            return
        z = self.zoom
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        full = QRectF(0, 0, self.pixmap.width() * z, self.pixmap.height() * z)
        p.drawPixmap(full, self.pixmap, QRectF(self.pixmap.rect()))
        if self.only_mode:  # dim everything that will NOT be processed
            shade = QPainterPath()
            shade.addRect(full)
            for r in self.regions:
                if r.kind == KEEP:
                    hole = QPainterPath()
                    hole.addRect(self._rect_w(r))
                    shade = shade.subtracted(hole)
            p.fillPath(shade, QColor(0, 0, 0, 125))
        for i, r in enumerate(self.regions):
            self._paint_region(p, r, i == self.sel)
        d = self._drag
        if d and d["mode"] == "new" and d["region"] is not None:
            self._paint_region(p, d["region"], False, dashed=True)

    def _paint_region(self, p: QPainter, r: Region, selected: bool, dashed: bool = False) -> None:
        color = COLORS[r.kind]
        rect = self._rect_w(r)
        fill = QColor(color)
        fill.setAlpha(70)
        p.fillRect(rect, fill)
        pen = QPen(color, 3 if selected else 2)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(rect)

        f = QFont(self.font())
        f.setBold(True)
        f.setPointSize(max(8, f.pointSize() - 1))
        p.setFont(f)
        fm = QFontMetrics(f)
        label = r.kind.upper() + (f": {r.name}" if r.name else "")
        tag = QRectF(rect.left(), rect.top(), fm.horizontalAdvance(label) + 10, fm.height() + 4)
        p.fillRect(tag, color)
        p.setPen(QColor("white"))
        p.drawText(tag, Qt.AlignmentFlag.AlignCenter, label)

        if selected:
            p.setPen(QPen(color, 2))
            p.setBrush(QColor("white"))
            cx, cy = rect.center().x(), rect.center().y()
            for x, y in [(rect.left(), rect.top()), (cx, rect.top()), (rect.right(), rect.top()),
                         (rect.left(), cy), (rect.right(), cy),
                         (rect.left(), rect.bottom()), (cx, rect.bottom()), (rect.right(), rect.bottom())]:
                p.drawRect(QRectF(x - 4, y - 4, 8, 8))
