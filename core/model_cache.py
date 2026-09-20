"""Point the OCR libraries' model caches at a folder chosen by the user."""
from __future__ import annotations

import os
from pathlib import Path


class ModelCache:
    """Sets (and later removes) the environment variables the OCR libraries read for their cache folder.

    The variables are read when a library is first imported, so a change made after a model was
    loaded only fully applies after restarting the app.
    """

    ENV: dict[str, str] = {           # variable -> sub-folder inside the chosen directory
        "PADDLE_PDX_CACHE_HOME": "paddlex",   # PaddleOCR / PaddleX
        "HF_HOME": "huggingface",             # Hugging Face (transformers, olmOCR weights ...)
        "MODEL_CACHE_DIR": "surya",           # Surya
        "DOCTR_CACHE_DIR": "doctr",           # docTR
    }

    def __init__(self) -> None:
        self._owned: set[str] = set()

    def apply(self, cache_dir: str) -> None:
        """Use ``cache_dir`` (empty string = back to each library's default; variables the user set are never touched)."""
        for var, sub in self.ENV.items():
            if cache_dir:
                os.environ[var] = str(Path(cache_dir) / sub)
                self._owned.add(var)
            elif var in self._owned:
                os.environ.pop(var, None)
                self._owned.discard(var)
