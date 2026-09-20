"""OptionsPanel: mode, backend, language, run scope, post-processing toggles and the Run / Cancel button."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QPushButton, QSpinBox, QStackedWidget, QVBoxLayout,
    QWidget,
)

from config.defaults import LLM_BACKENDS, MODES, NORMAL_BACKENDS
from config.manager import ConfigManager
from core.languages import language_names
from theme.theme_manager import ThemeManager
from ui.widgets import make_combo, set_combo


@dataclass
class RunSelection:
    """What the user chose in the options panel for the next run."""

    mode: str
    backend: str
    language: str
    all_pages: bool
    overlap_pct: int
    min_conf_pct: int
    dehyphenate: bool
    normalize_whitespace: bool
    page_headings: bool


class OptionsPanel(QWidget):
    """Right-hand controls. Choices that should survive restarts are saved to the config as they change.

    Signals: ``runClicked`` (Run or Cancel, depending on state), ``settingsRequested``.
    """

    runClicked = Signal()
    settingsRequested = Signal()

    def __init__(self, config: ConfigManager, theme: ThemeManager) -> None:
        super().__init__()
        self._config = config
        self._syncing = False
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox("Mode")
        bv = QVBoxLayout(box)
        self.cmb_mode = make_combo(MODES)
        bv.addWidget(self.cmb_mode)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        self.cmb_lang = make_combo([(n, n) for n in language_names()])
        self.cmb_lang.setToolTip("Auto = the engine's default multilingual model.\n"
                                 "Pick Korean (etc.) explicitly for best results on those scripts.")
        form.addRow("Language", self.cmb_lang)
        bv.addLayout(form)

        self.stack = QStackedWidget()
        page_normal = QWidget()
        fn = QFormLayout(page_normal)
        fn.setContentsMargins(0, 0, 0, 0)
        self.cmb_normal = make_combo(NORMAL_BACKENDS)
        self.spin_overlap = QSpinBox()
        self.spin_overlap.setRange(10, 100)
        self.spin_overlap.setSuffix(" %")
        self.spin_overlap.setToolTip("Discard a text box when at least this much of it lies inside an ignored area.")
        self.spin_conf = QSpinBox()
        self.spin_conf.setRange(0, 99)
        self.spin_conf.setSuffix(" %")
        self.spin_conf.setToolTip("Discard text the engine is less confident about than this (0 = keep everything).")
        fn.addRow("Backend", self.cmb_normal)
        fn.addRow("Ignore overlap \u2265", self.spin_overlap)
        fn.addRow("Min confidence", self.spin_conf)
        self.stack.addWidget(page_normal)
        page_llm = QWidget()
        fl = QFormLayout(page_llm)
        fl.setContentsMargins(0, 0, 0, 0)
        self.cmb_llm = make_combo(LLM_BACKENDS)
        btn_cfg = QPushButton("Server settings...")
        btn_cfg.clicked.connect(self.settingsRequested)
        fl.addRow("Backend", self.cmb_llm)
        fl.addRow("", btn_cfg)
        self.stack.addWidget(page_llm)
        bv.addWidget(self.stack)
        v.addWidget(box)

        row = QHBoxLayout()
        self.cmb_scope = QComboBox()
        self.cmb_scope.addItems(["All pages", "Current page only"])
        self.chk_headings = QCheckBox("Page headings")
        self.chk_headings.setChecked(True)
        row.addWidget(self.cmb_scope)
        row.addWidget(self.chk_headings)
        v.addLayout(row)
        row2 = QHBoxLayout()
        self.chk_dehyph = QCheckBox("De-hyphenate line breaks")
        self.chk_ws = QCheckBox("Normalize whitespace")
        row2.addWidget(self.chk_dehyph)
        row2.addWidget(self.chk_ws)
        v.addLayout(row2)

        self.btn_run = QPushButton("Run OCR")
        self.btn_run.setObjectName("runBtn")
        self._theme = theme
        theme.bind_icon(self.btn_run, "play")
        self.btn_run.clicked.connect(self.runClicked)
        v.addWidget(self.btn_run)

        self.cmb_mode.currentIndexChanged.connect(self.stack.setCurrentIndex)
        for w in (self.cmb_mode, self.cmb_lang, self.cmb_normal, self.cmb_llm):
            w.currentIndexChanged.connect(self._persist)
        for w in (self.spin_overlap, self.spin_conf):
            w.valueChanged.connect(self._persist)
        self.sync_from_config()

    # ---- config <-> widgets -------------------------------------------------------------
    def sync_from_config(self) -> None:
        """Load widget state from the config (used at start-up and after the settings dialog closes)."""
        c = self._config
        self._syncing = True
        try:
            set_combo(self.cmb_mode, c.get("mode"))
            set_combo(self.cmb_normal, c.get("normal_backend"))
            set_combo(self.cmb_llm, c.get("llm_backend"))
            set_combo(self.cmb_lang, c.get("language"))
            self.spin_overlap.setValue(int(c.get("overlap_pct")))
            self.spin_conf.setValue(int(c.get("min_conf_pct")))
            self.stack.setCurrentIndex(self.cmb_mode.currentIndex())
        finally:
            self._syncing = False

    def _persist(self, *_args) -> None:
        if self._syncing:
            return
        self._config.update({
            "mode": self.cmb_mode.currentData(), "normal_backend": self.cmb_normal.currentData(),
            "llm_backend": self.cmb_llm.currentData(), "language": self.cmb_lang.currentData(),
            "overlap_pct": self.spin_overlap.value(), "min_conf_pct": self.spin_conf.value(),
        })

    # ---- API used by the main window ----------------------------------------------------------
    def selection(self) -> RunSelection:
        """Snapshot of the current choices."""
        mode = self.cmb_mode.currentData()
        backend = (self.cmb_normal if mode == "normal" else self.cmb_llm).currentData()
        return RunSelection(mode, backend, self.cmb_lang.currentData(), self.cmb_scope.currentIndex() == 0,
                            self.spin_overlap.value(), self.spin_conf.value(), self.chk_dehyph.isChecked(),
                            self.chk_ws.isChecked(), self.chk_headings.isChecked())

    def set_running(self, running: bool) -> None:
        """Switch the main button between Run OCR and Cancel."""
        self.btn_run.setText("Cancel" if running else "Run OCR")
        self._theme.bind_icon(self.btn_run, "stop" if running else "play")
        self.btn_run.setProperty("running", running)
        self.btn_run.style().unpolish(self.btn_run)
        self.btn_run.style().polish(self.btn_run)
        self.btn_run.setEnabled(True)

    def set_cancelling(self) -> None:
        """Grey the button while a cancel is pending."""
        self.btn_run.setEnabled(False)
