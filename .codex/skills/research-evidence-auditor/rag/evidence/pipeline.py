"""End-to-end assembly of a validated evidence-audit report."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from rag.evidence.adapters import AdaptedEvidenceBatch, adapt_retrieval_sources
from rag.evidence.adjudication import adjudicate_claims
from rag.evidence.claim_alignment import align_claims_to_evidence
from rag.evidence.models import (
    Claim,
    ClaimStatus,
    EvidenceReport,
    ReportStatus,
    RunMetadata,
)


REFUSAL_ANSWER = "现有材料不足，无法对回答进行可靠的证据审计。"
QUERY_UNAVAILABLE_GAP = "知识库查询暂时不可用，本次未采纳任何未经证据核验的结论。"
QUERY_UNAVAILABLE_WARNING = "knowledge query unavailable; returned deterministic refusal"


def build_evidence_report(
    answer: str,
    retrieval_sources: Iterable[Mapping[str, Any]] | None,
    retrieval_strategy: str = "hybrid_rerank",
    answer_mode: str = "offline",
    duration_ms: int = 0,
    degraded_services: Iterable[str] | None = (),
) -> EvidenceReport:
    """Run normalization, alignment, adjudication, and report validation."""

    input_warnings: tuple[str, ...] = ()
    if retrieval_sources is None:
        source_items: tuple[Mapping[str, Any], ...] = ()
        input_warnings = ("retrieval sources were null and treated as empty",)
    else:
        try:
            source_items = tuple(retrieval_sources)
        except TypeError:
            source_items = ()
            input_warnings = ("retrieval sources were not iterable and treated as empty",)
    batch = adapt_retrieval_sources(source_items)
    normalized_answer = answer.strip() if isinstance(answer, str) else ""
    normalized_strategy = str(retrieval_strategy).strip() or "unknown"
    normalized_mode = str(answer_mode).strip() or "unknown"
    degraded = tuple(
        _deduplicate(
            str(item).strip()
            for item in (degraded_services or ())
            if item is not None and str(item).strip()
        )
    )
    batch_warnings = tuple(input_warnings) + tuple(batch.warnings)

    if not normalized_answer:
        return _refused_report(
            answer=REFUSAL_ANSWER,
            batch=batch,
            retrieval_strategy=normalized_strategy,
            answer_mode=normalized_mode,
            duration_ms=duration_ms,
            degraded_services=degraded,
            gaps=("待审计回答为空。",),
            warnings=batch_warnings,
        )

    if not batch.evidence:
        return _refused_report(
            answer=REFUSAL_ANSWER,
            batch=batch,
            retrieval_strategy=normalized_strategy,
            answer_mode=normalized_mode,
            duration_ms=duration_ms,
            degraded_services=degraded,
            gaps=("没有可用证据，原回答未被采纳为可靠结论。",),
            warnings=batch_warnings,
        )

    alignment = align_claims_to_evidence(normalized_answer, batch.evidence)
    if not alignment.claims:
        return _refused_report(
            answer=REFUSAL_ANSWER,
            batch=batch,
            retrieval_strategy=normalized_strategy,
            answer_mode=normalized_mode,
            duration_ms=duration_ms,
            degraded_services=degraded,
            gaps=("回答中没有可审计的原子主张。",),
            warnings=batch_warnings + tuple(alignment.warnings),
        )

    adjudication = adjudicate_claims(alignment, batch.evidence)
    gaps = _build_gaps(adjudication.claims)
    status = (
        ReportStatus.COMPLETE
        if all(claim.status is ClaimStatus.SUPPORTED for claim in adjudication.claims)
        else ReportStatus.PARTIAL
    )
    warnings = tuple(
        _deduplicate(batch_warnings + tuple(adjudication.warnings))
    )
    report = EvidenceReport(
        status=status,
        answer=normalized_answer,
        claims=adjudication.claims,
        evidence=batch.evidence,
        conflicts=adjudication.conflicts,
        gaps=gaps,
        sources=batch.sources,
        run_meta=RunMetadata(
            retrieval_strategy=normalized_strategy,
            answer_mode=normalized_mode,
            duration_ms=duration_ms,
            degraded_services=degraded,
            warnings=warnings,
        ),
        assessments=adjudication.assessments,
    )
    report.validate()
    return report


def build_evidence_report_from_qa_result(
    qa_result: Mapping[str, Any],
    retrieval_strategy: str = "hybrid_rerank",
    duration_ms: int = 0,
    degraded_services: Iterable[str] | None = (),
) -> EvidenceReport:
    """Adapt the existing ``answer_question`` response into an audit report."""

    if not isinstance(qa_result, Mapping):
        raise TypeError("qa_result must be a mapping")
    raw_sources = qa_result.get("sources", ())
    if not isinstance(raw_sources, (list, tuple)):
        raw_sources = ()
    return build_evidence_report(
        answer=str(qa_result.get("answer", "")),
        retrieval_sources=raw_sources,
        retrieval_strategy=retrieval_strategy,
        answer_mode=str(qa_result.get("mode", "unknown")) or "unknown",
        duration_ms=duration_ms,
        degraded_services=degraded_services,
    )


def build_degraded_evidence_report(
    *,
    duration_ms: int = 0,
    degraded_service: str = "knowledge_query",
) -> EvidenceReport:
    """Return a safe refusal when retrieval cannot produce an auditable result."""

    service = str(degraded_service).strip() or "knowledge_query"
    return _refused_report(
        answer=REFUSAL_ANSWER,
        batch=AdaptedEvidenceBatch(evidence=(), sources=(), warnings=()),
        retrieval_strategy="unavailable",
        answer_mode="degraded",
        duration_ms=duration_ms,
        degraded_services=(service,),
        gaps=(QUERY_UNAVAILABLE_GAP,),
        warnings=(QUERY_UNAVAILABLE_WARNING,),
    )


def _refused_report(
    answer: str,
    batch: AdaptedEvidenceBatch,
    retrieval_strategy: str,
    answer_mode: str,
    duration_ms: int,
    degraded_services: tuple[str, ...],
    gaps: tuple[str, ...],
    warnings: tuple[str, ...],
) -> EvidenceReport:
    report = EvidenceReport(
        status=ReportStatus.REFUSED,
        answer=answer,
        claims=(),
        evidence=batch.evidence,
        conflicts=(),
        gaps=gaps,
        sources=batch.sources,
        run_meta=RunMetadata(
            retrieval_strategy=retrieval_strategy,
            answer_mode=answer_mode,
            duration_ms=duration_ms,
            degraded_services=degraded_services,
            warnings=tuple(_deduplicate(warnings)),
        ),
        assessments=(),
    )
    report.validate()
    return report


def _build_gaps(claims: tuple[Claim, ...]) -> tuple[str, ...]:
    gaps: list[str] = []
    for claim in claims:
        if claim.status is ClaimStatus.INSUFFICIENT:
            gaps.append(f"结论“{claim.text}”缺少足以支持或反驳的证据。")
        elif claim.status is ClaimStatus.REFUTED:
            gaps.append(f"结论“{claim.text}”被当前证据反驳，需要修正。")
        elif claim.status is ClaimStatus.CONTESTED:
            gaps.append(f"结论“{claim.text}”存在相互冲突的证据，需要人工核验。")
    return tuple(gaps)


def _deduplicate(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
