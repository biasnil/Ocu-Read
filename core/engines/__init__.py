"""Engine implementations and the factory that builds them."""
from __future__ import annotations

from dataclasses import dataclass

from core.engines.llm_engine import LLMEngine, ServerConfig
from core.engines.normal_engine import NormalEngine
from core.languages import language_by_name
from core.ocr_engine import OCREngine


@dataclass(frozen=True)
class EngineSpec:
    """Everything that decides which engine gets built (hashable, so engines can be cached)."""

    mode: str                       # "normal" | "llm"
    backend: str                    # normal: auto|paddle|doctr   llm: surya|server
    language: str = "Auto"
    device: str = "auto"
    server: ServerConfig | None = None


class EngineFactory:
    """Creates engines and keeps loaded ones around so models aren't reloaded on every run."""

    def __init__(self) -> None:
        self._cache: dict[EngineSpec, OCREngine] = {}

    def create(self, spec: EngineSpec) -> OCREngine:
        """Return a (possibly cached) engine for ``spec``."""
        if spec not in self._cache:
            lang = language_by_name(spec.language)
            if spec.mode == "normal":
                self._cache[spec] = NormalEngine(lang, spec.backend, spec.device)
            else:
                self._cache[spec] = LLMEngine(spec.backend, spec.device, lang, spec.server)
        return self._cache[spec]

    def register(self, spec: EngineSpec, engine: OCREngine) -> None:
        """Use ``engine`` for ``spec`` (how plug-in engines and test doubles are added)."""
        self._cache[spec] = engine

    def clear(self) -> None:
        """Forget cached engines (after settings such as device or backend change)."""
        self._cache.clear()


__all__ = ["EngineFactory", "EngineSpec", "LLMEngine", "NormalEngine", "ServerConfig"]
