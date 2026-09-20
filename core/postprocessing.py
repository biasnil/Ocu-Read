"""Text clean-up after OCR: confidence filter, line assembly, de-hyphenation, whitespace."""
from __future__ import annotations

import re
import statistics
from dataclasses import replace

from core.models import OCRResult, RunOptions, TextBox


def filter_by_confidence(boxes: list[TextBox], min_conf: float) -> list[TextBox]:
    """Drop boxes below ``min_conf`` (0..1)."""
    return [b for b in boxes if b.conf >= min_conf]


def assemble_text(boxes: list[TextBox]) -> str:
    """Group boxes into lines (vertical overlap), order left-to-right, add paragraph gaps."""
    boxes = [b for b in boxes if b.text.strip()]
    if not boxes:
        return ""
    boxes = sorted(boxes, key=lambda b: (b.y0 + b.y1) / 2)
    lines: list[list[TextBox]] = []
    for b in boxes:
        if lines:
            cur = lines[-1]
            top, bot = min(x.y0 for x in cur), max(x.y1 for x in cur)
            overlap = min(bot, b.y1) - max(top, b.y0)
            if overlap > 0.5 * min(bot - top, b.y1 - b.y0):
                cur.append(b)
                continue
        lines.append([b])

    med_h = statistics.median(max(1.0, b.y1 - b.y0) for b in boxes)
    out: list[str] = []
    prev_bottom: float | None = None
    for line in lines:
        line.sort(key=lambda b: b.x0)
        parts = [line[0].text.strip()]
        for a, b in zip(line, line[1:]):
            parts.append("    " if b.x0 - a.x1 > 1.5 * med_h else " ")
            parts.append(b.text.strip())
        top = min(b.y0 for b in line)
        if prev_bottom is not None and top - prev_bottom > 0.8 * med_h:
            out.append("")
        out.append("".join(parts))
        prev_bottom = max(b.y1 for b in line)
    return "\n".join(out)


def dehyphenate(text: str) -> str:
    """Join words split by a hyphen at a line break ('exam-\\nple' -> 'example'). Letters only."""
    return re.sub(r"([^\W\d_])-\n[ \t]*([^\W\d_])", r"\1\2", text)


def normalize_whitespace(text: str) -> str:
    """Collapse runs of spaces, trim line ends, and squeeze 3+ blank lines to one."""
    text = re.sub(r"(?<=\S)[ \t]{2,}", " ", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text)


class PostProcessor:
    """Turns an engine's raw :class:`OCRResult` into final text according to :class:`RunOptions`."""

    def process(self, result: OCRResult, options: RunOptions) -> OCRResult:
        """Return a copy of ``result`` with ``boxes`` filtered and ``text`` filled in."""
        boxes = filter_by_confidence(result.boxes, options.min_confidence)
        text = result.text if result.text is not None else assemble_text(boxes)
        if options.dehyphenate:
            text = dehyphenate(text)
        if options.normalize_whitespace:
            text = normalize_whitespace(text)
        return replace(result, boxes=boxes, text=text)
