"""Evidence-audit domain contracts shared by the API, UI, and Skill package."""

from rag.evidence.adapters import AdaptedEvidenceBatch, adapt_retrieval_sources
from rag.evidence.claim_alignment import (
    AlignmentCandidate,
    ClaimAlignmentResult,
    align_claims_to_evidence,
    split_atomic_claims,
)
from rag.evidence.adjudication import (
    AdjudicationResult,
    adjudicate_claims,
)
from rag.evidence.conflict_detection import (
    ConflictKind,
    ConflictSignal,
    detect_conflict_signal,
)
from rag.evidence.pipeline import (
    build_degraded_evidence_report,
    build_evidence_report,
    build_evidence_report_from_qa_result,
)
from rag.evidence.reporting import render_evidence_report_markdown, report_to_dict
from rag.evidence.source_quality import (
    SourceQualityAssessment,
    assess_source_quality,
)
from rag.evidence.models import (
    Claim,
    ClaimEvidenceAssessment,
    ClaimStatus,
    Conflict,
    ContractValidationError,
    Evidence,
    EvidenceRelation,
    EvidenceReport,
    ReportStatus,
    RunMetadata,
    SourceLocator,
    SourceRecord,
)

__all__ = [
    "AdaptedEvidenceBatch",
    "AdjudicationResult",
    "AlignmentCandidate",
    "Claim",
    "ClaimStatus",
    "ConflictKind",
    "ConflictSignal",
    "ClaimAlignmentResult",
    "ClaimEvidenceAssessment",
    "Conflict",
    "ContractValidationError",
    "Evidence",
    "EvidenceRelation",
    "EvidenceReport",
    "ReportStatus",
    "RunMetadata",
    "SourceLocator",
    "SourceQualityAssessment",
    "SourceRecord",
    "adapt_retrieval_sources",
    "adjudicate_claims",
    "align_claims_to_evidence",
    "build_degraded_evidence_report",
    "build_evidence_report",
    "build_evidence_report_from_qa_result",
    "detect_conflict_signal",
    "render_evidence_report_markdown",
    "report_to_dict",
    "split_atomic_claims",
    "assess_source_quality",
]
