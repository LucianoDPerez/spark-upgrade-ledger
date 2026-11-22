"""Convert existing RAG retrieval output into the evidence-audit contract."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import PurePath
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from rag.evidence.models import (
    Evidence,
    EvidenceRelation,
    SourceLocator,
    SourceRecord,
)
from rag.evidence.source_quality import assess_source_quality


CHUNK_METADATA_FIELDS = {
    "block_line_end",
    "block_line_start",
    "call_targets",
    "called_by",
    "calls",
    "child_symbols",
    "imports",
    "line_end",
    "line_start",
    "module_path",
    "page_end",
    "page_start",
    "symbol_name",
    "symbol_type",
}


@dataclass(frozen=True)
class AdaptedEvidenceBatch:
    """Normalized retrieval evidence plus non-fatal conversion warnings."""

    sources: tuple[SourceRecord, ...]
    evidence: tuple[Evidence, ...]
    warnings: tuple[str, ...] = ()

    def validate(self) -> None:
        source_ids = {source.source_id for source in self.sources}
        if len(source_ids) != len(self.sources):
            raise ValueError("adapted sources contain duplicate IDs")
        evidence_ids = {item.evidence_id for item in self.evidence}
        if len(evidence_ids) != len(self.evidence):
            raise ValueError("adapted evidence contains duplicate IDs")
        for source in self.sources:
            source.validate()
        for item in self.evidence:
            item.validate()
            if item.source_id not in source_ids:
                raise ValueError(f"evidence references unknown source: {item.source_id}")


def adapt_retrieval_sources(
    retrieval_sources: Iterable[Mapping[str, Any]],
    relation: EvidenceRelation = EvidenceRelation.CONTEXT,
) -> AdaptedEvidenceBatch:
    """Normalize formatted RAG sources without depending on vector-store classes.

    Invalid individual records are skipped with warnings so one malformed search
    result cannot collapse the complete answer. Identifiers are content-derived
    and stable across repeated runs with the same inputs.
    """

    normalized_sources: dict[str, SourceRecord] = {}
    normalized_evidence: dict[str, Evidence] = {}
    warnings: list[str] = []

    for index, raw_source in enumerate(retrieval_sources, start=1):
        if not isinstance(raw_source, Mapping):
            warnings.append(f"retrieval source {index} is not an object and was skipped")
            continue

        content = _text(raw_source.get("content"))
        if not content:
            warnings.append(f"retrieval source {index} has no evidence text and was skipped")
            continue

        metadata = _mapping(raw_source.get("metadata"))
        source_path = _text(raw_source.get("source"))
        source_url = _text(raw_source.get("source_url")) or _text(metadata.get("source_url"))
        if not source_path and not source_url:
            warnings.append(f"retrieval source {index} has no path or URL and was skipped")
            continue

        path_value, url_value = _split_source_location(source_path, source_url)
        title = _text(raw_source.get("title")) or _source_title(source_path, source_url)
        source_type = _text(raw_source.get("doc_type")) or "unknown"
        source_id = _text(metadata.get("source_id")) or _stable_id(
            "source",
            source_type,
            path_value,
            url_value,
            title,
        )
        source_record = SourceRecord(
            source_id=source_id,
            title=title,
            source_type=source_type,
            path=path_value,
            url=url_value,
            metadata=_source_metadata(metadata),
        )

        existing_source = normalized_sources.get(source_id)
        if existing_source is None:
            normalized_sources[source_id] = source_record
        else:
            merged_source, has_conflict = _merge_source_records(
                existing_source,
                source_record,
            )
            normalized_sources[source_id] = merged_source
            if has_conflict:
                warnings.append(
                    f"source ID {source_id} has conflicting metadata; "
                    "the first non-empty values were kept"
                )

        chunk_id = _text(raw_source.get("chunk_id")) or "unknown"
        evidence_id = _text(raw_source.get("evidence_id")) or _stable_id(
            "evidence",
            source_id,
            chunk_id,
            content,
        )
        locator = SourceLocator(
            page_start=_positive_int(metadata.get("page_start")),
            page_end=_positive_int(metadata.get("page_end")),
            line_start=_positive_int(metadata.get("line_start")),
            line_end=_positive_int(metadata.get("line_end")),
            symbol=_text(metadata.get("symbol_name")),
            url=source_url,
        )
        locator = _repair_locator_ranges(locator)
        quality_assessment = assess_source_quality(
            raw_source,
            metadata,
            source_type=source_type,
            title=title,
            path=path_value,
            url=url_value,
            locator=locator,
            excerpt=content,
        )
        warnings.extend(
            f"retrieval source {index} {warning}"
            for warning in quality_assessment.warnings
        )
        evidence_metadata = _evidence_metadata(raw_source, metadata)
        evidence_metadata["quality_components"] = (
            quality_assessment.component_scores()
        )
        evidence_item = Evidence(
            evidence_id=evidence_id,
            source_id=source_id,
            excerpt=content,
            relation=relation,
            quality_score=quality_assessment.score,
            locator=locator,
            rationale=quality_assessment.rationale,
            metadata=evidence_metadata,
        )

        existing_evidence = normalized_evidence.get(evidence_id)
        if existing_evidence is None:
            normalized_evidence[evidence_id] = evidence_item
        elif existing_evidence != evidence_item:
            warnings.append(
                f"evidence ID {evidence_id} has conflicting content; the first record was kept"
            )

    batch = AdaptedEvidenceBatch(
        sources=tuple(normalized_sources.values()),
        evidence=tuple(normalized_evidence.values()),
        warnings=tuple(warnings),
    )
    batch.validate()
    return batch


def _stable_id(prefix: str, *parts: object) -> str:
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"), default=str)
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def _split_source_location(source_path: str, source_url: str) -> tuple[str, str]:
    if source_url:
        return source_path, source_url
    parsed = urlsplit(source_path)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        return "", source_path
    return source_path, ""


def _source_title(source_path: str, source_url: str) -> str:
    candidate = source_path or urlsplit(source_url).path
    name = PurePath(candidate.replace("\\", "/")).name
    return name or "未命名来源"


def _repair_locator_ranges(locator: SourceLocator) -> SourceLocator:
    page_end = locator.page_end
    line_end = locator.line_end
    if locator.page_start is None or (
        page_end is not None and page_end < locator.page_start
    ):
        page_end = locator.page_start
    if locator.line_start is None or (
        line_end is not None and line_end < locator.line_start
    ):
        line_end = locator.line_start
    return SourceLocator(
        page_start=locator.page_start,
        page_end=page_end,
        line_start=locator.line_start,
        line_end=line_end,
        symbol=locator.symbol,
        url=locator.url,
    )


def _evidence_metadata(
    raw_source: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    result = {
        "chunk_id": raw_source.get("chunk_id"),
        "retriever": raw_source.get("retriever"),
        "score": raw_source.get("score"),
        "base_score": raw_source.get("base_score"),
        "rerank_score": raw_source.get("rerank_score"),
        "vector_score": raw_source.get("vector_score"),
        "keyword_score": raw_source.get("keyword_score"),
        "query_intent": raw_source.get("query_intent"),
        "doi": metadata.get("doi"),
        "arxiv_id": metadata.get("arxiv_id"),
    }
    return _json_safe_mapping({key: value for key, value in result.items() if value is not None})


def _source_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    source_values = {
        key: value for key, value in metadata.items() if key not in CHUNK_METADATA_FIELDS
    }
    return _json_safe_mapping(source_values)


def _merge_source_records(
    existing: SourceRecord,
    incoming: SourceRecord,
) -> tuple[SourceRecord, bool]:
    existing_identity = (
        existing.title,
        existing.source_type,
        existing.path,
        existing.url,
    )
    incoming_identity = (
        incoming.title,
        incoming.source_type,
        incoming.path,
        incoming.url,
    )
    if existing_identity != incoming_identity:
        return existing, True

    metadata = dict(existing.metadata)
    has_conflict = False
    for key, value in incoming.metadata.items():
        previous = metadata.get(key)
        if _is_empty(previous):
            metadata[key] = value
        elif _is_empty(value) or previous == value:
            continue
        else:
            has_conflict = True
    return (
        SourceRecord(
            source_id=existing.source_id,
            title=existing.title,
            source_type=existing.source_type,
            path=existing.path,
            url=existing.url,
            metadata=metadata,
        ),
        has_conflict,
    )


def _is_empty(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _json_safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _json_safe(item) for key, item in value.items()}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return _json_safe_mapping(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return str(value)
