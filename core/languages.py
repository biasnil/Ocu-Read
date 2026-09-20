"""Languages offered to the user and how each engine family understands them."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    """A selectable OCR language."""

    name: str
    paddle_code: str | None   # None = let PaddleOCR choose its default multilingual model
    hint: str | None          # sentence fragment for LLM prompts (None = no hint)


LANGUAGES: tuple[Language, ...] = (
    Language("Auto", None, None),
    Language("English", "en", "English"),
    Language("Chinese (Simplified) + English", "ch", "Simplified Chinese and English"),
    Language("Chinese (Traditional)", "chinese_cht", "Traditional Chinese"),
    Language("Korean", "korean", "Korean"),
    Language("Japanese", "japan", "Japanese"),
)


def language_names() -> list[str]:
    """Names in display order."""
    return [lang.name for lang in LANGUAGES]


def language_by_name(name: str) -> Language:
    """Look a language up by display name (falls back to Auto)."""
    for lang in LANGUAGES:
        if lang.name == name:
            return lang
    return LANGUAGES[0]
