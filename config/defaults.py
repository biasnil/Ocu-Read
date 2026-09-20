"""Default value for every setting, plus the option tables the UI offers."""
from __future__ import annotations

CONFIG_VERSION = 1

# (label, stored value) pairs -------------------------------------------------------------
MODES = [("Normal - fast OCR engine", "normal"), ("LLM - vision-language model", "llm")]
NORMAL_BACKENDS = [("Auto (PaddleOCR, else docTR)", "auto"), ("PaddleOCR", "paddle"), ("docTR", "doctr")]
LLM_BACKENDS = [("Surya (local)", "surya"), ("olmOCR / OpenAI-compatible server", "server")]
DEVICES = [("Auto", "auto"), ("CPU", "cpu"), ("CUDA (NVIDIA GPU)", "cuda"), ("MPS (Apple Silicon)", "mps")]
EXPORT_FORMATS = [("Plain text (.txt)", "txt"), ("Markdown (.md)", "md"), ("JSON (.json)", "json")]
THEMES = [("Dark", "dark"), ("Light", "light")]
ROTATIONS = [("None", 0), ("90\u00B0 clockwise", 90), ("180\u00B0", 180), ("90\u00B0 counter-clockwise", 270)]

DEFAULT_LLM_PROMPT = (
    "Transcribe all text on this page in natural reading order. "
    "Render tables as Markdown tables. Output only the transcription, no commentary."
)

DEFAULTS: dict[str, object] = {
    "mode": "normal",
    "normal_backend": "auto",
    "llm_backend": "surya",
    "language": "Auto",
    "device": "auto",
    "cache_dir": "",
    "export_format": "txt",
    "theme": "dark",
    "overlap_pct": 50,
    "min_conf_pct": 0,
    "restore_sessions": True,
    "preprocess_rotate": 0,
    "preprocess_deskew": False,
    "preprocess_binarize": False,
    "llm_base_url": "http://localhost:8000/v1",
    "llm_model": "allenai/olmOCR-2-7B-1025",
    "llm_api_key": "",
    "llm_prompt": DEFAULT_LLM_PROMPT,
    "llm_max_side": 1288,
}
