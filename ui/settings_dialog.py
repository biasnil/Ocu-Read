"""SettingsDialog: everything in the config, opened from the gear icon."""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from config.defaults import (
    DEFAULT_LLM_PROMPT, DEFAULTS, DEVICES, EXPORT_FORMATS, LLM_BACKENDS, MODES, NORMAL_BACKENDS, ROTATIONS, THEMES,
)
from config.manager import ConfigManager
from core.languages import language_names
from ui.widgets import make_combo, set_combo


class SettingsDialog(QDialog):
    """Modal settings editor. Nothing is written until OK; 'Reset to defaults' only refills the fields."""

    def __init__(self, config: ConfigManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(600)
        self._config = config
        outer = QVBoxLayout(self)

        general = QGroupBox("General")
        gf = QFormLayout(general)
        self.mode = make_combo(MODES)
        self.normal_backend = make_combo(NORMAL_BACKENDS)
        self.llm_backend = make_combo(LLM_BACKENDS)
        self.language = make_combo([(n, n) for n in language_names()])
        self.device = make_combo(DEVICES)
        self.export = make_combo(EXPORT_FORMATS)
        self.theme = make_combo(THEMES)
        self.restore = QCheckBox("Restore a file's regions when I open it again")
        self.cache = QLineEdit()
        self.cache.setPlaceholderText("Default (each library's own cache folder)")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        cache_row = QHBoxLayout()
        cache_row.addWidget(self.cache, 1)
        cache_row.addWidget(browse)
        gf.addRow("Default mode", self.mode)
        gf.addRow("Normal-mode backend", self.normal_backend)
        gf.addRow("LLM-mode backend", self.llm_backend)
        gf.addRow("Language hint", self.language)
        gf.addRow("Device", self.device)
        gf.addRow("Model cache folder", cache_row)
        gf.addRow("Default export format", self.export)
        gf.addRow("Theme", self.theme)
        gf.addRow("", self.restore)
        note = QLabel("Device and cache-folder changes apply fully after restarting the app "
                      "if a model was already loaded this session.")
        note.setWordWrap(True)
        note.setProperty("muted", True)
        note.setMinimumHeight(2 * note.fontMetrics().height() + 6)
        gf.addRow(note)
        outer.addWidget(general)

        pre = QGroupBox("Image preprocessing (applied before OCR)")
        pf = QFormLayout(pre)
        self.rotate = make_combo(ROTATIONS)
        self.deskew = QCheckBox("Straighten skewed scans (deskew)")
        self.binarize = QCheckBox("Convert to black and white (binarize)")
        pf.addRow("Rotate", self.rotate)
        pf.addRow("", self.deskew)
        pf.addRow("", self.binarize)
        outer.addWidget(pre)

        server = QGroupBox("olmOCR / OpenAI-compatible server")
        sf = QFormLayout(server)
        self.url, self.model, self.key = QLineEdit(), QLineEdit(), QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.side = QSpinBox()
        self.side.setRange(512, 4096)
        self.prompt = QPlainTextEdit()
        self.prompt.setFixedHeight(80)
        sf.addRow("Base URL", self.url)
        sf.addRow("Model name", self.model)
        sf.addRow("API key (optional)", self.key)
        sf.addRow("Max image side (px)", self.side)
        sf.addRow("Prompt", self.prompt)
        outer.addWidget(server)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel |
                                   QDialogButtonBox.StandardButton.RestoreDefaults)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        reset = buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults)
        reset.setText("Reset to defaults")
        reset.clicked.connect(self._reset)
        outer.addWidget(buttons)
        self._load(config.get)

    def _load(self, get: Callable[[str], Any]) -> None:
        set_combo(self.mode, get("mode"))
        set_combo(self.normal_backend, get("normal_backend"))
        set_combo(self.llm_backend, get("llm_backend"))
        set_combo(self.language, get("language"))
        set_combo(self.device, get("device"))
        set_combo(self.export, get("export_format"))
        set_combo(self.theme, get("theme"))
        set_combo(self.rotate, get("preprocess_rotate"))
        self.restore.setChecked(bool(get("restore_sessions")))
        self.deskew.setChecked(bool(get("preprocess_deskew")))
        self.binarize.setChecked(bool(get("preprocess_binarize")))
        self.cache.setText(str(get("cache_dir")))
        self.url.setText(str(get("llm_base_url")))
        self.model.setText(str(get("llm_model")))
        self.key.setText(str(get("llm_api_key")))
        self.side.setValue(int(get("llm_max_side")))
        self.prompt.setPlainText(str(get("llm_prompt")))

    def _reset(self) -> None:
        self._load(lambda key: DEFAULTS[key])

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Model cache folder", self.cache.text())
        if folder:
            self.cache.setText(folder)

    def _save(self) -> None:
        self._config.update({
            "mode": self.mode.currentData(), "normal_backend": self.normal_backend.currentData(),
            "llm_backend": self.llm_backend.currentData(), "language": self.language.currentData(),
            "device": self.device.currentData(), "export_format": self.export.currentData(),
            "theme": self.theme.currentData(), "restore_sessions": self.restore.isChecked(),
            "preprocess_rotate": self.rotate.currentData(), "preprocess_deskew": self.deskew.isChecked(),
            "preprocess_binarize": self.binarize.isChecked(), "cache_dir": self.cache.text().strip(),
            "llm_base_url": self.url.text().strip(), "llm_model": self.model.text().strip(),
            "llm_api_key": self.key.text(), "llm_max_side": self.side.value(),
            "llm_prompt": self.prompt.toPlainText().strip() or DEFAULT_LLM_PROMPT,
        })
        self.accept()
