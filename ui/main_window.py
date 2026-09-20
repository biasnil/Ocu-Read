"""MainWindow: wires the panels together and drives file loading, OCR runs, sessions and export."""
from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent
from PySide6.QtCore import QMimeData, Qt, QTimer
from PySide6.QtGui import QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QMainWindow, QMessageBox, QSplitter, QTabWidget, QToolButton, QVBoxLayout,
    QWidget,
)

from core.engines import EngineSpec, ServerConfig
from core.models import OCRResult, PageJob, PreprocessOptions, RunOptions
from core.pipeline import OCRPipeline
from core.postprocessing import PostProcessor
from core.preprocessing import Preprocessor
from fileio.file_loader import SUPPORTED_EXTS, FileLoader
from ui.error_dialog import show_error
from ui.log_pane import LogPane
from ui.options_panel import OptionsPanel, RunSelection
from ui.pipeline_worker import PipelineWorker
from ui.preview_widget import PreviewWidget
from ui.progress_panel import ProgressPanel
from ui.region import RegionStore
from ui.region_list import RegionListWidget
from ui.results_panel import ResultsPanel
from ui.settings_dialog import SettingsDialog

if TYPE_CHECKING:  # avoids a circular import at run time
    from app import App

log = logging.getLogger(__name__)


def pil_to_qimage(img: Image.Image) -> QImage:
    """Deep-copied QImage from a PIL image."""
    img = img.convert("RGB")
    return QImage(img.tobytes(), img.width, img.height, img.width * 3, QImage.Format.Format_RGB888).copy()


class MainWindow(QMainWindow):
    """The application window. All long-lived services come from the ``App`` it is given."""

    def __init__(self, ctx: "App") -> None:
        super().__init__()
        self.ctx = ctx
        self.config = ctx.config
        self.theme = ctx.theme
        self.setWindowTitle("OcuRead")
        self.setAcceptDrops(True)
        self.loader: FileLoader | None = None
        self.store = RegionStore()
        self.page = 0
        self.page_size = (1, 1)
        self.worker: PipelineWorker | None = None
        self._running = False
        self._results: list[OCRResult] = []
        self._multi = False
        self._headings = True
        self._session_timer = QTimer(self)
        self._session_timer.setSingleShot(True)
        self._session_timer.setInterval(800)
        self._session_timer.timeout.connect(self.save_session)
        self._build_ui()
        self.log_pane.attach()
        QShortcut(QKeySequence.StandardKey.Open, self, activated=self.open_dialog)

    # ---- construction --------------------------------------------------------------------
    def _build_ui(self) -> None:
        split = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(split)

        self.preview = PreviewWidget(self.theme)
        split.addWidget(self.preview)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(3, 6, 6, 6)
        top = QHBoxLayout()
        top.addStretch(1)
        self.btn_theme, self.btn_gear = QToolButton(), QToolButton()
        for btn, icon, tip in ((self.btn_theme, "theme", "Switch dark / light theme"), (self.btn_gear, "gear", "Settings")):
            self.theme.bind_icon(btn, icon)
            btn.setToolTip(tip)
            top.addWidget(btn)
        rv.addLayout(top)

        self.options = OptionsPanel(self.config, self.theme)
        rv.addWidget(self.options)
        self.progress_panel = ProgressPanel()
        rv.addWidget(self.progress_panel)

        self.tabs = QTabWidget()
        self.results = ResultsPanel()
        self.region_list = RegionListWidget(self.theme)
        self.tabs.addTab(self.results, "Results")
        self.tabs.addTab(self.region_list, "Regions")
        rv.addWidget(self.tabs, 1)
        self.log_pane = LogPane()
        rv.addWidget(self.log_pane)
        split.addWidget(right)
        split.setSizes([760, 480])
        self.statusBar().showMessage("Drop a PDF or image to begin.")

        # wiring: widgets talk to each other only through signals handled here
        p = self.preview
        p.openRequested.connect(self.open_dialog)
        p.pageRequested.connect(self.goto)
        p.regionsChanged.connect(self.on_regions_changed)
        p.selectionChanged.connect(self.region_list.set_selected)
        p.onlyToggled.connect(self.on_only_toggled)
        p.applyAllToggled.connect(self.on_apply_all)
        self.region_list.selected.connect(p.canvas.select)
        self.region_list.deleteRequested.connect(self._delete_region)
        self.region_list.renamed.connect(p.canvas.rename_region)
        self.options.runClicked.connect(self.on_run_clicked)
        self.options.settingsRequested.connect(self.open_settings)
        self.results.exportRequested.connect(self.export_output)
        self.results.copied.connect(lambda: self.statusBar().showMessage("Copied to clipboard."))
        self.btn_gear.clicked.connect(self.open_settings)
        self.btn_theme.clicked.connect(self.theme.toggle)

    # ---- settings ------------------------------------------------------------------------
    def open_settings(self) -> None:
        """Show the settings dialog and apply the result."""
        if self._running:
            QMessageBox.information(self, "OCR running", "Change settings after the current run finishes.")
            return
        if SettingsDialog(self.config, self).exec():
            self.ctx.model_cache.apply(str(self.config.get("cache_dir")))
            self.theme.apply()
            self.options.sync_from_config()
            self.ctx.engines.clear()  # rebuild engines with the new backend / device
            self.statusBar().showMessage("Settings saved.")

    # ---- drag & drop ---------------------------------------------------------------------
    @staticmethod
    def _first_supported(mime: QMimeData) -> str | None:
        for url in mime.urls():
            path = url.toLocalFile()
            if path and Path(path).suffix.lower() in SUPPORTED_EXTS:
                return path
        return None

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasUrls() and self._first_supported(e.mimeData()):
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent) -> None:
        path = self._first_supported(e.mimeData())
        if path:
            e.acceptProposedAction()
            self.load_file(path)

    # ---- files and pages -----------------------------------------------------------------
    def open_dialog(self) -> None:
        """Ask for a PDF or image."""
        exts = " ".join(f"*{x}" for x in sorted(SUPPORTED_EXTS))
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF or image", "", f"PDF / images ({exts});;All files (*)")
        if path:
            self.load_file(path)

    def load_file(self, path: str) -> None:
        """Open ``path``, restoring its saved regions if there are any."""
        if self._running:
            QMessageBox.information(self, "OCR running", "Wait for the current OCR run to finish (or cancel it) first.")
            return
        if Path(path).suffix.lower() not in SUPPORTED_EXTS:
            self.statusBar().showMessage("Unsupported file type.")
            return
        try:
            loader = FileLoader(path)
        except Exception as ex:  # noqa: BLE001
            show_error(self, "Can't open file", str(ex), traceback.format_exc())
            return
        self.save_session()
        if self.loader:
            self.loader.close()
        self.loader, self.store = loader, RegionStore()
        restored = 0
        if self.config.get("restore_sessions"):
            saved = self.ctx.sessions.load(path, loader.page_count)
            if saved:
                self.store = RegionStore.from_dict(saved)
                restored = self.store.count()
        self._results.clear()
        self.results.clear()
        self.progress_panel.reset()
        self.preview.set_page_count(loader.page_count)
        self.preview.set_flags(self.store.only, self.store.shared)
        self.preview.reset_zoom()
        self.page = -1
        self.show_page(0)
        self.setWindowTitle(f"OcuRead - {Path(path).name}")
        n = loader.page_count
        msg = f"Loaded {Path(path).name} ({n} page{'s' if n != 1 else ''})."
        if restored:
            msg += f" Restored {restored} region(s) from your last session."
        self.statusBar().showMessage(msg)
        log.info(msg)

    def goto(self, index: int) -> None:
        """Show page ``index`` if it exists."""
        if self.loader and 0 <= index < self.loader.page_count and index != self.page:
            self.show_page(index)
        else:
            self.preview.sync_page_spin(self.page)

    def show_page(self, index: int) -> None:
        """Render and display page ``index`` with its regions."""
        try:
            img = self.loader.render(index)
        except Exception as ex:  # noqa: BLE001
            show_error(self, "Can't render page", str(ex), traceback.format_exc())
            return
        self.page, self.page_size = index, img.size
        regions = self.store.get(index, img.size)
        self.preview.show_page(pil_to_qimage(img), regions, index)
        self.region_list.set_regions(regions)

    # ---- regions -------------------------------------------------------------------------
    def on_regions_changed(self) -> None:
        """Store the canvas regions, refresh the sidebar, schedule a session save."""
        canvas = self.preview.canvas
        self.store.set(self.page, self.page_size, canvas.regions)
        self.region_list.set_regions(canvas.regions, canvas.sel)
        self._session_timer.start()

    def _delete_region(self, index: int) -> None:
        self.preview.canvas.select(index)
        self.preview.canvas.delete_selected()

    def on_only_toggled(self, on: bool) -> None:
        """Only mode switched."""
        self.store.only = on
        self._session_timer.start()
        self.statusBar().showMessage(
            "Only: just the Keep regions will be processed (Ignore regions are redundant while this is on)."
            if on else "Only off: unmarked areas count as Keep.")

    def on_apply_all(self, checked: bool) -> None:
        """Apply-to-all-pages switched."""
        if not self.loader:
            return
        if checked:
            self.store.enable_shared(self.page, self.page_size, self.preview.regions)
            self.statusBar().showMessage(f"Regions from page {self.page + 1} now apply to every page.")
        else:
            self.store.disable_shared([self.loader.page_size(i) for i in range(self.loader.page_count)])
            self.statusBar().showMessage("Regions are per-page again (each page keeps its current regions).")
        self._session_timer.start()

    def save_session(self) -> None:
        """Persist the current file's regions (or delete the session when there are none)."""
        self._session_timer.stop()
        if not self.loader or not self.config.get("restore_sessions"):
            return
        try:
            if self.store.count() == 0 and not self.store.only:
                self.ctx.sessions.delete(self.loader.path)
            else:
                self.ctx.sessions.save(self.loader.path, self.loader.page_count, self.store.to_dict())
        except OSError as ex:
            log.warning("Couldn't save session: %s", ex)

    # ---- running OCR ---------------------------------------------------------------------
    def _engine_spec(self, sel: RunSelection) -> EngineSpec:
        c = self.config
        server = None
        if sel.mode == "llm" and sel.backend == "server":
            server = ServerConfig(str(c.get("llm_base_url")), str(c.get("llm_model")), str(c.get("llm_api_key")),
                                  str(c.get("llm_prompt")), int(c.get("llm_max_side")))
        return EngineSpec(sel.mode, sel.backend, sel.language, str(c.get("device")), server)

    def on_run_clicked(self) -> None:
        """Start a run, or cancel the one in progress."""
        if self._running:
            if self.worker:
                self.worker.cancel()
            self.options.set_cancelling()
            self.statusBar().showMessage("Cancelling after the current page...")
            return
        if not self.loader:
            self.statusBar().showMessage("Open a PDF or image first.")
            return
        sel = self.options.selection()
        pages = list(range(self.loader.page_count)) if sel.all_pages else [self.page]
        if self.store.only:
            missing = [str(p + 1) for p in pages if not self.store.has_keep(p)]
            if missing:
                shown = ", ".join(missing[:8]) + (" ..." if len(missing) > 8 else "")
                answer = QMessageBox.question(
                    self, "Only is on",
                    f"Only is on, but page(s) {shown} have no Keep region, so they will produce no text.\n\nRun anyway?")
                if answer != QMessageBox.StandardButton.Yes:
                    return
        engine = self.ctx.engines.create(self._engine_spec(sel))
        cfg = self.config
        pipeline = OCRPipeline(
            engine,
            Preprocessor(PreprocessOptions(int(cfg.get("preprocess_rotate")), bool(cfg.get("preprocess_deskew")),
                                           bool(cfg.get("preprocess_binarize")))),
            PostProcessor(), self.ctx.tqdm_bridge)
        options = RunOptions(sel.overlap_pct / 100.0, sel.min_conf_pct / 100.0, sel.dehyphenate,
                             sel.normalize_whitespace, self.store.only)
        jobs = [PageJob(p, self.store.get(p, self.loader.page_size(p))) for p in pages]
        self._multi, self._headings = len(pages) > 1, sel.page_headings
        self._results.clear()
        self.results.clear()
        if self.worker:
            self.worker.wait()
        self.worker = PipelineWorker(pipeline, self.loader.path, jobs, options)
        self.worker.progress.connect(self.progress_panel.on_update)
        self.worker.resultReady.connect(self._on_result)
        self.worker.failed.connect(lambda msg, tb: show_error(self, "OCR failed", msg, tb))
        self.worker.ended.connect(self._on_ended)
        log.info("Run started: %d page(s), %s", len(pages), engine.label)
        self._running = True
        self.options.set_running(True)
        self.progress_panel.start()
        self.worker.start()

    def _on_result(self, result: OCRResult) -> None:
        self._results.append(result)
        self.results.append_page(result.page_index, result.text or "", self._multi and self._headings)

    def _on_ended(self, status: str) -> None:
        self._running = False
        self.options.set_running(False)
        self.progress_panel.finish(status)
        self.statusBar().showMessage({"done": "Done.", "cancelled": "Cancelled.", "failed": "Failed."}[status])

    # ---- export --------------------------------------------------------------------------
    def export_output(self) -> None:
        """Save the results as .txt / .md / .json, or an annotated PDF of the regions."""
        ext = str(self.config.get("export_format"))
        stem = Path(self.loader.path).stem if self.loader else "ocr_output"
        filters = {"txt": "Text (*.txt)", "md": "Markdown (*.md)", "json": "JSON (*.json)",
                   "pdf": "Annotated PDF (*.pdf)"}
        path, chosen = QFileDialog.getSaveFileName(self, "Export", f"{stem}.{ext}", ";;".join(filters.values()),
                                                   filters.get(ext, filters["txt"]))
        if not path:
            return
        p = Path(path)
        if not p.suffix:
            p = p.with_suffix(next((f".{k}" for k, v in filters.items() if v == chosen), ".txt"))
        try:
            if p.suffix.lower() == ".json":
                if not self._results:
                    QMessageBox.information(self, "Nothing to export", "Run OCR first - JSON export includes per-page boxes.")
                    return
                self.ctx.exporter.export_json(p, self._results, self.loader.path if self.loader else "")
            elif p.suffix.lower() == ".pdf":
                if not self.loader:
                    QMessageBox.information(self, "Nothing to export", "Open a file first.")
                    return
                self._export_annotated_pdf(p)
            else:
                self.ctx.exporter.export_text(p, self.results.text())
        except Exception as ex:  # noqa: BLE001
            show_error(self, "Export failed", str(ex), traceback.format_exc())
            return
        self.statusBar().showMessage(f"Saved {p}")

    def _export_annotated_pdf(self, path: Path) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            def progress(done: int, total: int) -> None:
                self.statusBar().showMessage(f"Annotated PDF: page {done} / {total}")
                QApplication.processEvents()

            self.ctx.exporter.export_annotated_pdf(
                path, self.loader, lambda i, size: self.store.get(i, size), self.store.only, progress)
        finally:
            QApplication.restoreOverrideCursor()

    # ---- shutdown ------------------------------------------------------------------------
    def closeEvent(self, e: QCloseEvent) -> None:
        if self._running and self.worker:
            self.worker.cancel()
        if self.worker:
            self.worker.wait(5000)
        self.save_session()
        self.log_pane.detach()
        if self.loader:
            self.loader.close()
        super().closeEvent(e)
