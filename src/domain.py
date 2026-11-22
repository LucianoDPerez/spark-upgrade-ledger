"""Pure entities. No framework or I/O imports."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field


class ValidationError(Exception):
    """An expected, safe-to-return validation failure."""


class GenerationError(Exception):
    """The model or the audit step could not produce usable output."""


def normalize(text: str) -> str:
    """Whitespace-normalised text used for grounding and cache keys."""
    return re.sub(r"\s+", " ", text).strip()


def normalize_quote(text: str) -> str:
    """Strip the prompt's [line-number] prefix, then whitespace-normalise."""
    return normalize(re.sub(r"^\[\d+\]\s*", "", text.strip()))


def cache_key(*parts: str) -> str:
    payload = "\x1f".join(normalize(p) for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceLine:
    number: int
    text: str

    def as_block(self) -> str:
        return f"[{self.number}] {self.text}"


@dataclass(frozen=True)
class SourceDocument:
    name: str
    url: str
    lines: tuple[SourceLine, ...]

    def as_prompt(self) -> str:
        return "\n".join(line.as_block() for line in self.lines)

    def normalized_text(self) -> str:
        return normalize(" ".join(line.text for line in self.lines))

    def find_lines(self, quote: str) -> tuple[int, int]:
        needle = normalize_quote(quote)
        for line in self.lines:
            if needle in normalize(line.text):
                return line.number, line.number
        return 0, 0


@dataclass(frozen=True)
class ChecklistItem:
    id: str
    title: str
    affects: str
    source_quote: str
    breaking: bool
    line_start: int = 0
    line_end: int = 0


@dataclass(frozen=True)
class Review:
    decision: str
    corrected_text: str = ""


def is_approved(review: Review | None) -> bool:
    """Only an explicit accept or a non-empty correction counts as approval."""
    if review is None:
        return False
    if review.decision == "accept":
        return True
    if review.decision == "correct" and review.corrected_text.strip():
        return True
    return False


def build_exports(result: "ChecklistResult", reviews: dict[str, Review]) -> tuple[dict, dict]:
    """Return (final approved checklist, full human review log)."""
    common = {
        "source": result.source_name,
        "lang": result.lang,
        "audit_status": result.audit.get("status", ""),
    }
    final = {
        **common,
        "approved": [
            {
                **item.__dict__,
                "generated_title": item.title,
                "decision": reviews.get(item.id, Review("pending")).decision,
                "corrected_text": reviews.get(item.id, Review("pending")).corrected_text,
            }
            for item in result.items
            if is_approved(reviews.get(item.id))
        ],
    }
    log = {
        **common,
        "items": [
            {
                **item.__dict__,
                "generated_title": item.title,
                "decision": reviews.get(item.id, Review("pending")).decision,
                "corrected_text": reviews.get(item.id, Review("pending")).corrected_text,
                "approved": is_approved(reviews.get(item.id)),
            }
            for item in result.items
        ],
    }
    return final, log


@dataclass(frozen=True)
class ValidationOutcome:
    items: tuple[ChecklistItem, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChecklistResult:
    source_name: str
    items: tuple[ChecklistItem, ...]
    raw_output: str
    lang: str = "es"
    audit: dict = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    duration_ms: int = 0
    reviews: dict[str, Review] = field(default_factory=dict)

    def approved_items(self) -> tuple[ChecklistItem, ...]:
        out = []
        for item in self.items:
            if is_approved(self.reviews.get(item.id)):
                out.append(item)
        return tuple(out)
