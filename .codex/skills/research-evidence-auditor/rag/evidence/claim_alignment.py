"""Deterministic atomic-claim extraction and candidate-evidence alignment."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Iterable

from rag.evidence.models import Claim, ClaimStatus, Evidence


CLAIM_BOUNDARY = re.compile(r"(?:[。！？!?；;]+|(?<=[.!?])\s+|[\r\n]+)")
LIST_PREFIX = re.compile(
    r"^\s*(?:(?:[-*•])|(?:\d+[.)、])|(?:[一二三四五六七八九十]+[、.]))\s*"
)
SECTION_PREFIX = re.compile(r"^\s*(?:结论|依据|建议|回答|分析|证据)\s*[:：]\s*")
ENGLISH_TOKEN = re.compile(r"[a-z][a-z0-9_+.-]*|\d+(?:\.\d+)?%?", re.IGNORECASE)
CHINESE_SEQUENCE = re.compile(r"[\u4e00-\u9fff]+")
NUMBER_TOKEN = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?")
NON_CLAIM_HINTS = (
    "当前没有检测到可用的",
    "先返回检索版回答",
    "知识库中最相关的资料片段如下",
    "配置可用的模型 api key",
    "整理成更自然的中文回答",
)
IGNORED_TERMS = {
    "a",
    "an",
    "一个",
    "以及",
    "但是",
    "可以",
    "因为",
    "如果",
    "对于",
    "我们",
    "这个",
    "这些",
    "进行",
    "通过",
    "the",
    "and",
    "are",
    "as",
    "be",
    "for",
    "in",
    "is",
    "of",
    "on",
    "that",
    "this",
    "to",
    "was",
    "were",
    "with",
}


@dataclass(frozen=True)
class AlignmentCandidate:
    claim_id: str
    evidence_id: str
    alignment_score: float
    shared_terms: tuple[str, ...] = ()
    exact_numbers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClaimAlignmentResult:
    """Claims and relevant evidence candidates awaiting semantic adjudication."""

    claims: tuple[Claim, ...]
    candidates: tuple[AlignmentCandidate, ...]
    warnings: tuple[str, ...] = ()


def split_atomic_claims(answer: str, min_length: int = 4) -> tuple[str, ...]:
    """Split prose or list output into stable, deduplicated atomic claims."""

    if min_length < 1:
        raise ValueError("min_length must be at least 1")
    if not isinstance(answer, str) or not answer.strip():
        return ()

    claims: list[str] = []
    seen: set[str] = set()
    for part in CLAIM_BOUNDARY.split(answer):
        normalized = LIST_PREFIX.sub("", part).strip(" \t-—:：,，。；;")
        normalized = SECTION_PREFIX.sub("", normalized).strip(" \t-—:：,，。；;")
        normalized = re.sub(r"\s+", " ", normalized)
        if len(normalized) < min_length:
            continue
        if _is_non_claim_text(normalized):
            continue
        fingerprint = normalized.casefold()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        claims.append(normalized)
    return tuple(claims)


def _is_non_claim_text(text: str) -> bool:
    normalized = text.casefold()
    return any(hint in normalized for hint in NON_CLAIM_HINTS)


def align_claims_to_evidence(
    answer: str,
    evidence: Iterable[Evidence],
    min_alignment_score: float = 0.22,
    max_evidence_per_claim: int = 3,
) -> ClaimAlignmentResult:
    """Find lexically relevant evidence without deciding support or contradiction.

    Claims remain ``insufficient`` until a later adjudication stage determines
    whether candidate evidence supports, contradicts, or merely mentions them.
    """

    if not 0 <= min_alignment_score <= 1:
        raise ValueError("min_alignment_score must be between 0 and 1")
    if max_evidence_per_claim < 1:
        raise ValueError("max_evidence_per_claim must be at least 1")

    claim_texts = split_atomic_claims(answer)
    evidence_items = tuple(evidence)
    warnings: list[str] = []
    if not claim_texts:
        warnings.append("answer contains no atomic claims")
    if not evidence_items:
        warnings.append("no evidence is available for claim alignment")

    claims: list[Claim] = []
    all_candidates: list[AlignmentCandidate] = []
    for claim_text in claim_texts:
        claim_id = _stable_claim_id(claim_text)
        ranked = _rank_evidence(claim_id, claim_text, evidence_items)
        selected = tuple(
            candidate
            for candidate in ranked
            if candidate.alignment_score >= min_alignment_score
        )[:max_evidence_per_claim]
        if not selected:
            warnings.append(f"claim {claim_id} has no aligned evidence")
        all_candidates.extend(selected)
        claims.append(
            Claim(
                claim_id=claim_id,
                text=claim_text,
                status=ClaimStatus.INSUFFICIENT,
                confidence=0.0,
                evidence_ids=tuple(item.evidence_id for item in selected),
            )
        )

    return ClaimAlignmentResult(
        claims=tuple(claims),
        candidates=tuple(all_candidates),
        warnings=tuple(warnings),
    )


def _rank_evidence(
    claim_id: str,
    claim_text: str,
    evidence_items: tuple[Evidence, ...],
) -> list[AlignmentCandidate]:
    claim_terms = _terms(claim_text)
    claim_numbers = _numbers(claim_text)
    ranked: list[AlignmentCandidate] = []
    for item in evidence_items:
        evidence_terms = _terms(item.excerpt)
        shared_terms = claim_terms & evidence_terms
        coverage = len(shared_terms) / len(claim_terms) if claim_terms else 0.0
        union = claim_terms | evidence_terms
        jaccard = len(shared_terms) / len(union) if union else 0.0
        exact_numbers = claim_numbers & _numbers(item.excerpt)
        number_bonus = 0.15 if claim_numbers and exact_numbers else 0.0
        retrieval_score = _normalized_retrieval_score(item)
        score = min(
            1.0,
            0.65 * coverage
            + 0.2 * jaccard
            + 0.1 * retrieval_score
            + 0.05 * item.quality_score
            + number_bonus,
        )
        ranked.append(
            AlignmentCandidate(
                claim_id=claim_id,
                evidence_id=item.evidence_id,
                alignment_score=round(score, 6),
                shared_terms=tuple(sorted(shared_terms)[:20]),
                exact_numbers=tuple(sorted(exact_numbers)),
            )
        )
    return sorted(
        ranked,
        key=lambda item: (-item.alignment_score, item.evidence_id),
    )


def _terms(text: str) -> set[str]:
    normalized = text.casefold()
    terms = {token for token in ENGLISH_TOKEN.findall(normalized)}
    for sequence in CHINESE_SEQUENCE.findall(normalized):
        if len(sequence) == 1:
            terms.add(sequence)
        else:
            terms.update(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return {term for term in terms if term not in IGNORED_TERMS}


def _numbers(text: str) -> set[str]:
    return {token.casefold() for token in NUMBER_TOKEN.findall(text)}


def _normalized_retrieval_score(item: Evidence) -> float:
    for field_name in ("rerank_score", "score", "base_score"):
        raw_value = item.metadata.get(field_name)
        if raw_value is None or isinstance(raw_value, bool):
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError, OverflowError):
            continue
        return min(1.0, max(0.0, value))
    return 0.0


def _stable_claim_id(text: str) -> str:
    digest = sha256(text.casefold().encode("utf-8")).hexdigest()[:16]
    return f"claim-{digest}"
