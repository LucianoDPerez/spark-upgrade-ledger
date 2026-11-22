"""Conservative deterministic adjudication for aligned claims and evidence."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Iterable

from rag.evidence.claim_alignment import AlignmentCandidate, ClaimAlignmentResult
from rag.evidence.conflict_detection import detect_conflict_signal, numbers
from rag.evidence.models import (
    Claim,
    ClaimEvidenceAssessment,
    ClaimStatus,
    Conflict,
    Evidence,
    EvidenceRelation,
)


NUMBER_TOKEN = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?")
ENGLISH_CONTEXT_TOKEN = re.compile(r"[a-z][a-z0-9_+.-]*", re.IGNORECASE)
CHINESE_CONTEXT_SEQUENCE = re.compile(r"[\u4e00-\u9fff]+")
CONTEXT_STOP_TERMS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "for",
    "in",
    "is",
    "of",
    "on",
    "the",
    "to",
    "was",
    "were",
}
@dataclass(frozen=True)
class AdjudicationResult:
    claims: tuple[Claim, ...]
    assessments: tuple[ClaimEvidenceAssessment, ...]
    conflicts: tuple[Conflict, ...]
    warnings: tuple[str, ...] = ()


def adjudicate_claims(
    alignment: ClaimAlignmentResult,
    evidence: Iterable[Evidence],
    support_threshold: float = 0.4,
    contradiction_threshold: float = 0.3,
) -> AdjudicationResult:
    """Classify candidate evidence and update claim status conservatively.

    Deterministic rules only make a strong decision when there is an exact
    numeric match, a single-value numeric mismatch, an explicit negation
    mismatch, an opposite direction marker, or strong lexical alignment.
    """

    for field_name, value in (
        ("support_threshold", support_threshold),
        ("contradiction_threshold", contradiction_threshold),
    ):
        if not 0 <= value <= 1:
            raise ValueError(f"{field_name} must be between 0 and 1")

    evidence_by_id = {item.evidence_id: item for item in evidence}
    candidates_by_claim: dict[str, list[AlignmentCandidate]] = {}
    warnings = list(alignment.warnings)
    for candidate in alignment.candidates:
        if candidate.evidence_id not in evidence_by_id:
            warnings.append(
                f"candidate references unknown evidence: {candidate.evidence_id}"
            )
            continue
        candidates_by_claim.setdefault(candidate.claim_id, []).append(candidate)

    adjudicated_claims: list[Claim] = []
    assessments: list[ClaimEvidenceAssessment] = []
    conflicts: list[Conflict] = []
    for claim in alignment.claims:
        claim_assessments = [
            _assess_candidate(
                claim,
                evidence_by_id[candidate.evidence_id],
                candidate,
                support_threshold,
                contradiction_threshold,
            )
            for candidate in candidates_by_claim.get(claim.claim_id, [])
        ]
        assessments.extend(claim_assessments)
        supports = [
            item
            for item in claim_assessments
            if item.relation is EvidenceRelation.SUPPORTS
        ]
        contradictions = [
            item
            for item in claim_assessments
            if item.relation is EvidenceRelation.CONTRADICTS
        ]

        claim_conflicts: tuple[str, ...] = ()
        suspected = [
            item for item in claim_assessments if item.rationale.startswith("疑似冲突：")
        ]
        if supports and contradictions:
            conflict = _build_conflict(claim, supports, contradictions)
            conflicts.append(conflict)
            claim_conflicts = (conflict.conflict_id,)
            status = ClaimStatus.CONTESTED
        elif supports and suspected:
            conflict = _build_suspected_conflict(claim, supports, suspected)
            conflicts.append(conflict)
            claim_conflicts = (conflict.conflict_id,)
            status = ClaimStatus.INSUFFICIENT
        elif supports:
            status = ClaimStatus.SUPPORTED
        elif contradictions:
            status = ClaimStatus.REFUTED
        else:
            status = ClaimStatus.INSUFFICIENT

        confidence = max(
            (item.confidence for item in claim_assessments),
            default=0.0,
        )
        adjudicated_claims.append(
            Claim(
                claim_id=claim.claim_id,
                text=claim.text,
                status=status,
                confidence=round(confidence, 6),
                evidence_ids=tuple(item.evidence_id for item in claim_assessments),
                conflict_ids=claim_conflicts,
            )
        )

    return AdjudicationResult(
        claims=tuple(adjudicated_claims),
        assessments=tuple(assessments),
        conflicts=tuple(conflicts),
        warnings=tuple(_deduplicate(warnings)),
    )


def _assess_candidate(
    claim: Claim,
    evidence: Evidence,
    candidate: AlignmentCandidate,
    support_threshold: float,
    contradiction_threshold: float,
) -> ClaimEvidenceAssessment:
    claim_numbers = numbers(claim.text)
    evidence_numbers = numbers(evidence.excerpt)
    score = candidate.alignment_score
    has_shared_context = _has_shared_context(
        claim.text,
        evidence.excerpt,
        candidate,
    )

    signal = detect_conflict_signal(
        claim.text,
        evidence.excerpt,
        alignment_score=score,
        has_shared_context=has_shared_context and score >= contradiction_threshold,
    )
    if signal is not None:
        return _assessment(
            claim,
            evidence,
            signal.relation,
            max(signal.confidence_floor, score),
            _with_match_points(signal.rationale, candidate),
        )

    if has_shared_context and claim_numbers and claim_numbers & evidence_numbers:
        return _assessment(
            claim,
            evidence,
            EvidenceRelation.SUPPORTS,
            max(0.7, score),
            _with_match_points("结论与证据包含相同的明确数值", candidate),
        )

    if score >= support_threshold:
        return _assessment(
            claim,
            evidence,
            EvidenceRelation.SUPPORTS,
            score,
            _with_match_points("结论与证据具有较高文本对齐度且未发现显式冲突", candidate),
        )

    return _assessment(
        claim,
        evidence,
        EvidenceRelation.INSUFFICIENT,
        score,
        _with_match_points("证据与结论相关，但不足以确定支持或反驳", candidate),
    )


def _with_match_points(rationale: str, candidate: AlignmentCandidate) -> str:
    details: list[str] = []
    if candidate.shared_terms:
        details.append("共同关键词：" + "、".join(candidate.shared_terms[:6]))
    if candidate.exact_numbers:
        details.append("相同数值：" + "、".join(candidate.exact_numbers[:4]))
    if not details:
        return rationale
    return f"{rationale}（{'；'.join(details)}）"


def _has_shared_context(
    claim_text: str,
    evidence_text: str,
    candidate: AlignmentCandidate,
) -> bool:
    """Require a shared non-numeric concept before strong numeric decisions."""

    if candidate.shared_terms:
        return any(
            not NUMBER_TOKEN.fullmatch(term) and term not in CONTEXT_STOP_TERMS
            for term in candidate.shared_terms
        )
    return bool(_context_terms(claim_text) & _context_terms(evidence_text))


def _context_terms(text: str) -> set[str]:
    normalized = text.casefold()
    terms = {
        token
        for token in ENGLISH_CONTEXT_TOKEN.findall(normalized)
        if token not in CONTEXT_STOP_TERMS
    }
    for sequence in CHINESE_CONTEXT_SEQUENCE.findall(normalized):
        if len(sequence) == 1:
            terms.add(sequence)
        else:
            terms.update(
                sequence[index : index + 2]
                for index in range(len(sequence) - 1)
            )
    return terms


def _assessment(
    claim: Claim,
    evidence: Evidence,
    relation: EvidenceRelation,
    confidence: float,
    rationale: str,
) -> ClaimEvidenceAssessment:
    return ClaimEvidenceAssessment(
        claim_id=claim.claim_id,
        evidence_id=evidence.evidence_id,
        relation=relation,
        confidence=round(min(1.0, max(0.0, confidence)), 6),
        rationale=rationale,
    )


def _build_conflict(
    claim: Claim,
    supports: list[ClaimEvidenceAssessment],
    contradictions: list[ClaimEvidenceAssessment],
) -> Conflict:
    support = max(supports, key=lambda item: (item.confidence, item.evidence_id))
    contradiction = max(
        contradictions,
        key=lambda item: (item.confidence, item.evidence_id),
    )
    evidence_ids = tuple(sorted((support.evidence_id, contradiction.evidence_id)))
    digest_input = f"{claim.claim_id}|{'|'.join(evidence_ids)}"
    conflict_id = f"conflict-{sha256(digest_input.encode('utf-8')).hexdigest()[:16]}"
    return Conflict(
        conflict_id=conflict_id,
        summary=f"关于“{claim.text}”的候选证据同时出现支持与反驳信号。",
        severity=round((support.confidence + contradiction.confidence) / 2, 6),
        claim_ids=(claim.claim_id,),
        evidence_ids=evidence_ids,
        resolution="核对来源版本、统计口径、时间范围和原始上下文后再下结论。",
    )


def _build_suspected_conflict(
    claim: Claim,
    supports: list[ClaimEvidenceAssessment],
    suspected: list[ClaimEvidenceAssessment],
) -> Conflict:
    support = max(supports, key=lambda item: (item.confidence, item.evidence_id))
    uncertain = max(suspected, key=lambda item: (item.confidence, item.evidence_id))
    evidence_ids = tuple(sorted((support.evidence_id, uncertain.evidence_id)))
    digest_input = f"suspected|{claim.claim_id}|{'|'.join(evidence_ids)}"
    conflict_id = f"conflict-{sha256(digest_input.encode('utf-8')).hexdigest()[:16]}"
    return Conflict(
        conflict_id=conflict_id,
        summary=f"疑似冲突：关于“{claim.text}”的材料来自不同时间或版本。",
        severity=round(min(0.6, (support.confidence + uncertain.confidence) / 2), 6),
        claim_ids=(claim.claim_id,),
        evidence_ids=evidence_ids,
        resolution="先核对材料版本、发布日期和适用时间，再决定采用哪一项结论。",
    )
def _deduplicate(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))
