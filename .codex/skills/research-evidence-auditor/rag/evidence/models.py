"""Stable, dependency-free contracts for evidence-audit results.

Keep this module free of FastAPI, Pydantic, vector-store, and LLM imports. The
same structures are consumed by the backend, the competition Skill scripts,
the report renderer, and deterministic evaluation tools.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable


class ContractValidationError(ValueError):
    """Raised when an evidence report violates the public result contract."""


class EvidenceRelation(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXT = "context"
    INSUFFICIENT = "insufficient"


class ClaimStatus(str, Enum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    CONTESTED = "contested"
    INSUFFICIENT = "insufficient"


class ReportStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    REFUSED = "refused"


def _require_text(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{field_name} must be a non-empty string")


def _require_score(field_name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractValidationError(f"{field_name} must be a number between 0 and 1")
    if not 0.0 <= float(value) <= 1.0:
        raise ContractValidationError(f"{field_name} must be between 0 and 1")


def _require_positive_optional(field_name: str, value: int | None) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
        raise ContractValidationError(f"{field_name} must be a positive integer when provided")


def _require_unique(field_name: str, values: Iterable[str]) -> None:
    values_list = list(values)
    if len(values_list) != len(set(values_list)):
        raise ContractValidationError(f"{field_name} must not contain duplicate values")


@dataclass(frozen=True)
class SourceLocator:
    """Precise human-verifiable position inside a source."""

    page_start: int | None = None
    page_end: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    symbol: str = ""
    url: str = ""

    def validate(self) -> None:
        for field_name in ("page_start", "page_end", "line_start", "line_end"):
            _require_positive_optional(field_name, getattr(self, field_name))
        if self.page_end is not None and self.page_start is None:
            raise ContractValidationError("page_end requires page_start")
        if self.line_end is not None and self.line_start is None:
            raise ContractValidationError("line_end requires line_start")
        if self.page_start is not None and self.page_end is not None and self.page_end < self.page_start:
            raise ContractValidationError("page_end must not be smaller than page_start")
        if self.line_start is not None and self.line_end is not None and self.line_end < self.line_start:
            raise ContractValidationError("line_end must not be smaller than line_start")


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    title: str
    source_type: str
    path: str = ""
    url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        _require_text("source_id", self.source_id)
        _require_text("title", self.title)
        _require_text("source_type", self.source_type)
        if not self.path.strip() and not self.url.strip():
            raise ContractValidationError("source must provide path or url")


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    source_id: str
    excerpt: str
    relation: EvidenceRelation
    quality_score: float
    locator: SourceLocator = field(default_factory=SourceLocator)
    rationale: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        _require_text("evidence_id", self.evidence_id)
        _require_text("evidence.source_id", self.source_id)
        _require_text("evidence.excerpt", self.excerpt)
        if not isinstance(self.relation, EvidenceRelation):
            raise ContractValidationError("evidence.relation must be an EvidenceRelation")
        _require_score("evidence.quality_score", self.quality_score)
        self.locator.validate()


@dataclass(frozen=True)
class Claim:
    claim_id: str
    text: str
    status: ClaimStatus
    confidence: float
    evidence_ids: tuple[str, ...] = ()
    conflict_ids: tuple[str, ...] = ()

    def validate(self) -> None:
        _require_text("claim_id", self.claim_id)
        _require_text("claim.text", self.text)
        if not isinstance(self.status, ClaimStatus):
            raise ContractValidationError("claim.status must be a ClaimStatus")
        _require_score("claim.confidence", self.confidence)
        _require_unique("claim.evidence_ids", self.evidence_ids)
        _require_unique("claim.conflict_ids", self.conflict_ids)
        if self.status in {
            ClaimStatus.SUPPORTED,
            ClaimStatus.REFUTED,
            ClaimStatus.CONTESTED,
        } and not self.evidence_ids:
            raise ContractValidationError(
                f"{self.status.value} claim must reference evidence"
            )
        if self.status is ClaimStatus.CONTESTED and not self.conflict_ids:
            raise ContractValidationError("contested claim must reference a conflict")


@dataclass(frozen=True)
class ClaimEvidenceAssessment:
    claim_id: str
    evidence_id: str
    relation: EvidenceRelation
    confidence: float
    rationale: str

    def validate(self) -> None:
        _require_text("assessment.claim_id", self.claim_id)
        _require_text("assessment.evidence_id", self.evidence_id)
        if not isinstance(self.relation, EvidenceRelation):
            raise ContractValidationError(
                "assessment.relation must be an EvidenceRelation"
            )
        _require_score("assessment.confidence", self.confidence)
        _require_text("assessment.rationale", self.rationale)


@dataclass(frozen=True)
class Conflict:
    conflict_id: str
    summary: str
    severity: float
    claim_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    resolution: str = ""

    def validate(self) -> None:
        _require_text("conflict_id", self.conflict_id)
        _require_text("conflict.summary", self.summary)
        _require_score("conflict.severity", self.severity)
        _require_unique("conflict.claim_ids", self.claim_ids)
        _require_unique("conflict.evidence_ids", self.evidence_ids)
        if not self.claim_ids:
            raise ContractValidationError("conflict must reference at least one claim")
        if len(self.evidence_ids) < 2:
            raise ContractValidationError("conflict must reference at least two evidence items")


@dataclass(frozen=True)
class RunMetadata:
    retrieval_strategy: str
    answer_mode: str
    duration_ms: int = 0
    degraded_services: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def validate(self) -> None:
        _require_text("run_meta.retrieval_strategy", self.retrieval_strategy)
        _require_text("run_meta.answer_mode", self.answer_mode)
        if isinstance(self.duration_ms, bool) or not isinstance(self.duration_ms, int) or self.duration_ms < 0:
            raise ContractValidationError("run_meta.duration_ms must be a non-negative integer")
        _require_unique("run_meta.degraded_services", self.degraded_services)


@dataclass(frozen=True)
class EvidenceReport:
    status: ReportStatus
    answer: str
    claims: tuple[Claim, ...]
    evidence: tuple[Evidence, ...]
    conflicts: tuple[Conflict, ...]
    gaps: tuple[str, ...]
    sources: tuple[SourceRecord, ...]
    run_meta: RunMetadata
    assessments: tuple[ClaimEvidenceAssessment, ...] = ()

    def validate(self) -> None:
        if not isinstance(self.status, ReportStatus):
            raise ContractValidationError("report.status must be a ReportStatus")
        _require_text("report.answer", self.answer)
        _require_unique("claim IDs", (item.claim_id for item in self.claims))
        _require_unique("evidence IDs", (item.evidence_id for item in self.evidence))
        _require_unique("conflict IDs", (item.conflict_id for item in self.conflicts))
        _require_unique("source IDs", (item.source_id for item in self.sources))
        _require_unique(
            "assessment claim/evidence pairs",
            (f"{item.claim_id}:{item.evidence_id}" for item in self.assessments),
        )

        for item in self.claims:
            item.validate()
        for item in self.evidence:
            item.validate()
        for item in self.conflicts:
            item.validate()
        for item in self.sources:
            item.validate()
        for item in self.assessments:
            item.validate()
        self.run_meta.validate()

        claim_ids = {item.claim_id for item in self.claims}
        evidence_ids = {item.evidence_id for item in self.evidence}
        conflict_ids = {item.conflict_id for item in self.conflicts}
        source_ids = {item.source_id for item in self.sources}

        for item in self.claims:
            self._require_references("claim.evidence_ids", item.evidence_ids, evidence_ids)
            self._require_references("claim.conflict_ids", item.conflict_ids, conflict_ids)
        for item in self.evidence:
            self._require_references("evidence.source_id", (item.source_id,), source_ids)
        for item in self.conflicts:
            self._require_references("conflict.claim_ids", item.claim_ids, claim_ids)
            self._require_references("conflict.evidence_ids", item.evidence_ids, evidence_ids)
        for item in self.assessments:
            self._require_references("assessment.claim_id", (item.claim_id,), claim_ids)
            self._require_references(
                "assessment.evidence_id",
                (item.evidence_id,),
                evidence_ids,
            )

        if self.status is ReportStatus.COMPLETE and not self.claims:
            raise ContractValidationError("complete report must contain at least one claim")
        if self.status is ReportStatus.REFUSED and self.claims:
            raise ContractValidationError("refused report must not contain claims")

    @staticmethod
    def _require_references(field_name: str, values: Iterable[str], valid_ids: set[str]) -> None:
        missing = sorted(set(values) - valid_ids)
        if missing:
            raise ContractValidationError(f"{field_name} contains unknown IDs: {', '.join(missing)}")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation using stable string enum values."""

        self.validate()
        return asdict(self)
