"""Deterministic, fail-closed gates for the Spark draft."""

from __future__ import annotations

import json
import re

from .config import MAX_ITEMS
from .domain import (
    ChecklistItem,
    SourceDocument,
    ValidationError,
    ValidationOutcome,
    normalize,
    normalize_quote,
)

_ITEM_KEYS = {"id", "title", "affects", "source_quote", "breaking"}
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
_NEGATION_RE = re.compile(
    r"(?:\b(no|not|never|none|without|neither|nor|sin|nunca)\b)|(不|没有|未|无法|非)",
    re.IGNORECASE,
)
_AFFIRM_RE = re.compile(
    r"(?:\b(soporta|supported|enabled|habilitado|disponible|available|funciona|works)\b)"
    r"|(支持|可用|启用|正常|兼容)",
    re.IGNORECASE,
)
_ID_RE = re.compile(r"^C\d{1,2}$")


def parse_draft(raw: str) -> dict:
    if not isinstance(raw, str) or not raw.strip():
        raise ValidationError("Empty model output.")
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError("Model output was not valid JSON.") from exc
    if not isinstance(payload, dict) or set(payload) != {"items"}:
        raise ValidationError("Output schema mismatch: expected exactly 'items'.")
    return payload


def _limited_text(value: object, field: str, limit: int = 240) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"Field '{field}' must be a string.")
    text = value.strip()
    if not text:
        raise ValidationError(f"Field '{field}' must not be empty.")
    if len(text) > limit:
        raise ValidationError(f"Field '{field}' exceeds {limit} chars.")
    return text


def validate_draft(payload: dict, source: SourceDocument) -> ValidationOutcome:
    """Validate structure, invented numbers, quote grounding and negation.

    Grounding is line-level: a quote must match exactly ONE original line.
    Quotes spanning two lines are rejected, line numbers are assigned here,
    and a second item from the same line is dropped with a warning.
    """
    items_raw = payload.get("items")
    if not isinstance(items_raw, list):
        raise ValidationError("'items' must be an array.")
    if not 1 <= len(items_raw) <= MAX_ITEMS:
        raise ValidationError(f"'items' must have 1 to {MAX_ITEMS} entries.")

    source_norm = source.normalized_text()
    source_numbers = set(_NUMBER_RE.findall(source_norm))
    seen_ids: set[str] = set()
    seen_lines: set[int] = set()
    items: list[ChecklistItem] = []
    warnings: list[str] = []

    for position, raw in enumerate(items_raw, start=1):
        if not isinstance(raw, dict) or set(raw) != _ITEM_KEYS:
            raise ValidationError(f"Item {position} has an invalid schema.")
        item_id = raw["id"]
        if not isinstance(item_id, str) or not _ID_RE.fullmatch(item_id):
            raise ValidationError(f"Item {position} has an invalid id.")
        if item_id in seen_ids:
            raise ValidationError(f"Duplicate id {item_id}.")
        seen_ids.add(item_id)

        title = _limited_text(raw["title"], "title")
        affects = _limited_text(raw["affects"], "affects")
        quote = _limited_text(raw["source_quote"], "source_quote", limit=400)
        breaking = raw["breaking"]
        if not isinstance(breaking, bool):
            raise ValidationError(f"Item {item_id}: 'breaking' must be boolean.")

        grounded = normalize_quote(quote)
        matched_lines = [
            line for line in source.lines if grounded in normalize(line.text)
        ]
        if not matched_lines:
            raise ValidationError(f"Item {item_id}: source_quote is not grounded in a single line.")
        if len(matched_lines) > 1:
            raise ValidationError(f"Item {item_id}: source_quote is ambiguous across lines.")
        line_start = matched_lines[0].number
        if line_start <= 0:
            raise ValidationError(f"Item {item_id}: invalid source line number.")
        if line_start in seen_lines:
            warnings.append(f"Item {item_id}: duplicate source line dropped (one claim per line).")
            continue
        seen_lines.add(line_start)

        for number in _NUMBER_RE.findall(f"{title} {affects}"):
            if number not in source_numbers:
                raise ValidationError(f"Item {item_id}: invented number {number}.")

        if _NEGATION_RE.search(quote) and _AFFIRM_RE.search(f"{title} {affects}"):
            raise ValidationError(f"Item {item_id}: negation inverted in the summary.")

        items.append(
            ChecklistItem(
                id=item_id,
                title=title,
                affects=affects,
                source_quote=quote,
                breaking=breaking,
                line_start=line_start,
                line_end=line_start,
            )
        )
    if not items:
        raise ValidationError("No verifiable items remained after deduplication.")
    return ValidationOutcome(items=tuple(items), warnings=tuple(warnings))
