"""Explainable, deterministic quality scoring for retrieved evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any
from urllib.parse import urlsplit

from rag.evidence.models import SourceLocator


SOURCE_TYPE_VERIFIABILITY = {
    "paper": 0.75,
    "pdf": 0.70,
    "code": 0.70,
    "repository": 0.65,
    "markdown": 0.55,
    "text": 0.50,
    "txt": 0.50,
    "web": 0.45,
    "unknown": 0.35,
}
COMPONENT_LABELS = {
    "verifiability": "来源可核验性",
    "traceability": "定位完整性",
    "retrieval_relevance": "检索相关性",
    "excerpt_integrity": "片段完整性",
    "external_quality": "外部质量信号",
}


@dataclass(frozen=True)
class SourceQualityAssessment:
    """Quality score plus auditable components and non-fatal warnings."""

    score: float
    components: tuple[tuple[str, float], ...]
    rationale: str
    warnings: tuple[str, ...] = ()

    def validate(self) -> None:
        if not 0 <= self.score <= 1:
            raise ValueError("source quality score must be between 0 and 1")
        component_names = [name for name, _ in self.components]
        if len(component_names) != len(set(component_names)):
            raise ValueError("source quality components must be unique")
        for name, value in self.components:
            if name not in COMPONENT_LABELS or not 0 <= value <= 1:
                raise ValueError(f"invalid source quality component: {name}")
        if not self.rationale.strip():
            raise ValueError("source quality rationale must not be empty")

    def component_scores(self) -> dict[str, float]:
        return dict(self.components)


def assess_source_quality(
    raw_source: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    source_type: str,
    title: str,
    path: str,
    url: str,
    locator: SourceLocator,
    excerpt: str,
) -> SourceQualityAssessment:
    """Score evidence quality without claiming that a source is factually true.

    The score measures how reviewable and useful a retrieved excerpt is. It
    combines provenance signals, precise location, retrieval relevance, excerpt
    integrity, and an optional upstream quality score.
    """

    warnings: list[str] = []
    external_quality, external_field = _external_quality(raw_source, metadata)
    if external_field and external_quality is None:
        warnings.append(
            f"invalid external quality field {external_field} was ignored"
        )

    components = {
        "verifiability": _verifiability_score(source_type, path, url, metadata),
        "traceability": _traceability_score(
            title,
            path,
            url,
            locator,
            metadata,
        ),
        "retrieval_relevance": _retrieval_relevance(raw_source),
        "excerpt_integrity": _excerpt_integrity(excerpt),
    }
    if external_quality is None:
        weights = {
            "verifiability": 0.30,
            "traceability": 0.35,
            "retrieval_relevance": 0.20,
            "excerpt_integrity": 0.15,
        }
    else:
        components["external_quality"] = external_quality
        weights = {
            "verifiability": 0.20,
            "traceability": 0.25,
            "retrieval_relevance": 0.10,
            "excerpt_integrity": 0.10,
            "external_quality": 0.35,
        }

    rounded_components = tuple(
        (name, round(_clamp(value), 6)) for name, value in components.items()
    )
    score = round(
        sum(dict(rounded_components)[name] * weight for name, weight in weights.items()),
        6,
    )
    rationale_parts = [
        f"{COMPONENT_LABELS[name]} {value:.2f}"
        for name, value in rounded_components
    ]
    assessment = SourceQualityAssessment(
        score=score,
        components=rounded_components,
        rationale=f"综合来源质量评分 {score:.2f}（{'、'.join(rationale_parts)}）",
        warnings=tuple(warnings),
    )
    assessment.validate()
    return assessment


def _verifiability_score(
    source_type: str,
    path: str,
    url: str,
    metadata: Mapping[str, Any],
) -> float:
    normalized_type = source_type.strip().casefold() or "unknown"
    score = SOURCE_TYPE_VERIFIABILITY.get(normalized_type, 0.40)
    if _text(metadata.get("doi")) or _text(metadata.get("arxiv_id")):
        score += 0.15
    if _is_http_url(url):
        score += 0.05
    elif path.strip():
        score += 0.02
    return _clamp(score)


def _traceability_score(
    title: str,
    path: str,
    url: str,
    locator: SourceLocator,
    metadata: Mapping[str, Any],
) -> float:
    score = 0.0
    if path.strip() or _is_http_url(url):
        score += 0.30
    if title.strip():
        score += 0.10
    if locator.page_start is not None or locator.line_start is not None:
        score += 0.35
    if locator.symbol.strip():
        score += 0.10
    if _text(metadata.get("doi")) or _text(metadata.get("arxiv_id")):
        score += 0.15
    return _clamp(score)


def _retrieval_relevance(raw_source: Mapping[str, Any]) -> float:
    for field_name in ("rerank_score", "score", "base_score"):
        normalized = _normalize_score(raw_source.get(field_name))
        if normalized is not None:
            return normalized
    return 0.35


def _excerpt_integrity(excerpt: str) -> float:
    length = len(excerpt.strip())
    if length < 10:
        return 0.20
    if length < 40:
        return 0.65
    if length <= 4000:
        return 1.0
    if length <= 12000:
        return 0.80
    return 0.60


def _external_quality(
    raw_source: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> tuple[float | None, str]:
    for field_name, container in (
        ("quality_score", metadata),
        ("source_quality_score", raw_source),
    ):
        if field_name not in container or container.get(field_name) in (None, ""):
            continue
        return _normalize_score(container.get(field_name)), field_name
    return None, ""


def _normalize_score(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(score) or score < 0:
        return None
    if score > 1:
        if score > 100:
            return None
        score /= 100
    return _clamp(score)


def _is_http_url(value: str) -> bool:
    parsed = urlsplit(value.strip())
    return parsed.scheme.casefold() in {"http", "https"} and bool(parsed.netloc)


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, float(value)))
