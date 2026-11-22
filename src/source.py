"""Deterministic release-note parser with line provenance."""

from __future__ import annotations

import re
from pathlib import Path

from .config import MAX_INPUT_CHARS, MAX_SOURCE_LINES, MIN_INPUT_CHARS
from .domain import SourceDocument, SourceLine, ValidationError

_URL_RE = re.compile(r"^\s*URL:\s*(\S+)\s*$", re.MULTILINE)


def parse_source(text: str, name: str = "release_notes.txt") -> SourceDocument:
    if not isinstance(text, str):
        raise ValidationError("Source must be a string.")
    if len(text) < MIN_INPUT_CHARS:
        raise ValidationError(f"Source is too short ({MIN_INPUT_CHARS} chars minimum).")
    if len(text) > MAX_INPUT_CHARS:
        raise ValidationError(f"Source exceeds {MAX_INPUT_CHARS} chars.")

    match = _URL_RE.search(text)
    url = match.group(1) if match else ""
    body = _URL_RE.sub("", text).strip()
    lines = tuple(
        SourceLine(number=i, text=raw.strip())
        for i, raw in enumerate(body.splitlines(), start=1)
        if raw.strip()
    )
    if not lines:
        raise ValidationError("Source has no content lines.")
    if len(lines) > MAX_SOURCE_LINES:
        raise ValidationError(f"Source exceeds {MAX_SOURCE_LINES} lines.")
    return SourceDocument(name=name, url=url, lines=lines)


def load_source(path: Path) -> SourceDocument:
    return parse_source(path.read_text(encoding="utf-8"), name=path.name)
