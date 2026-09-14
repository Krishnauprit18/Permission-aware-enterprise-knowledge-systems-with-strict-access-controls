"""Deterministic, policy-bearing evidence objects for the protected P13 flow."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from math import isfinite

from knowledge_system.domain.contracts import EvidenceId
from knowledge_system.domain.persistence import Classification
from knowledge_system.domain.retrieval import RetrievalCandidate


class EvidenceResolutionError(RuntimeError):
    """Evidence cannot be resolved without violating its deterministic contract."""


class EvidenceDecisionStatus(StrEnum):
    """Trusted business-state semantics; content text never assigns these values."""

    INFORMATIONAL = "INFORMATIONAL"
    TENTATIVE = "TENTATIVE"
    APPROVED = "APPROVED"
    COMMITTED = "COMMITTED"


class EvidenceFreshness(StrEnum):
    """Trusted lifecycle/freshness state for a source revision."""

    CURRENT = "CURRENT"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"
    UNKNOWN = "UNKNOWN"


class EvidenceAnnotation(StrEnum):
    """Deterministic qualifications retained with evidence, never inferred by an LLM."""

    CURRENT = "CURRENT"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"
    SUPERSEDES = "SUPERSEDES"
    CONFLICTING = "CONFLICTING"
    LOWER_AUTHORITY = "LOWER_AUTHORITY"
    TENTATIVE = "TENTATIVE"
    APPROVED = "APPROVED"
    COMMITTED = "COMMITTED"


@dataclass(frozen=True, slots=True)
class EvidencePolicyMetadata:
    """Trusted metadata used for authority/freshness policy, separate from text."""

    authority_level: int
    effective_at: datetime
    freshness: EvidenceFreshness = EvidenceFreshness.UNKNOWN
    decision_status: EvidenceDecisionStatus = EvidenceDecisionStatus.INFORMATIONAL
    lifecycle_status: str = "ACTIVE"
    conflict_group: str | None = None
    is_current: bool = False
    supersedes_document_ids: tuple[str, ...] = ()
    superseded_by_document_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.authority_level < 0:
            raise ValueError("authority level must not be negative")
        if (
            self.effective_at.tzinfo is None
            or self.effective_at.utcoffset() != UTC.utcoffset(self.effective_at)
        ):
            raise ValueError("effective timestamp must be UTC-aware")
        object.__setattr__(self, "effective_at", self.effective_at.astimezone(UTC))
        if self.lifecycle_status != "ACTIVE":
            raise ValueError("only active evidence can enter resolution")
        if self.conflict_group is not None and not self.conflict_group.strip():
            raise ValueError("conflict group cannot be empty")
        for document_id in (
            *self.supersedes_document_ids,
            *self.superseded_by_document_ids,
        ):
            if not document_id.strip():
                raise ValueError("supersession document IDs cannot be empty")
        if self.is_current and self.freshness is EvidenceFreshness.SUPERSEDED:
            raise ValueError("superseded evidence cannot be current")


@dataclass(frozen=True, slots=True)
class EvidenceMaterial:
    """Authorized source text and trusted metadata for exactly one P12 candidate."""

    candidate: RetrievalCandidate
    text: str
    policy: EvidencePolicyMetadata

    def __post_init__(self) -> None:
        if not self.candidate.authorization.allowed or not self.text.strip():
            raise EvidenceResolutionError(
                "evidence material must be authorized and non-empty"
            )


@dataclass(frozen=True, slots=True)
class RerankScore:
    """A local pairwise ranking result for an already-authorized evidence ID."""

    evidence_id: EvidenceId
    score: float

    def __post_init__(self) -> None:
        if not isfinite(self.score):
            raise ValueError("rerank score must be finite")


@dataclass(frozen=True, slots=True)
class EvidenceRankDiagnostics:
    """Internal-only relevance and deterministic policy rationale."""

    retrieval_rank: int
    rerank_rank: int
    rerank_score: float | None
    fallback_used: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.retrieval_rank < 1 or self.rerank_rank < 1:
            raise ValueError("ranking positions must be positive")
        if self.rerank_score is not None and not isfinite(self.rerank_score):
            raise ValueError("rerank score must be finite")


@dataclass(frozen=True, slots=True)
class EvidenceResolutionInput:
    """A sanitized, reauthorized input to deterministic evidence policy."""

    material: EvidenceMaterial
    evidence_id: EvidenceId
    sanitized_text: str
    retrieval_rank: int
    rerank_rank: int
    rerank_score: float | None
    fallback_used: bool

    def __post_init__(self) -> None:
        if not self.sanitized_text.strip():
            raise EvidenceResolutionError("evidence resolution text must not be empty")
        if self.retrieval_rank < 1 or self.rerank_rank < 1:
            raise EvidenceResolutionError("evidence ranks must be positive")
        if self.rerank_score is not None and not isfinite(self.rerank_score):
            raise EvidenceResolutionError("rerank score must be finite")


@dataclass(frozen=True, slots=True)
class EvidencePacket:
    """Resolved authorized evidence; diagnostics are retained only for trace use."""

    evidence_id: EvidenceId
    chunk_id: str
    document_id: str
    document_version_id: str
    sanitized_text: str
    source_type: str
    source_locator: tuple[str, ...]
    source_url: str | None
    updated_at: datetime
    effective_at: datetime
    authority_level: int
    freshness: EvidenceFreshness
    decision_status: EvidenceDecisionStatus
    classification: Classification
    external_shareable: bool
    conflict_group: str | None
    supersedes_document_ids: tuple[str, ...]
    superseded_by_document_ids: tuple[str, ...]
    annotations: tuple[EvidenceAnnotation, ...]
    authorization_fingerprint: str
    diagnostics: EvidenceRankDiagnostics

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                str(self.evidence_id),
                self.chunk_id,
                self.document_id,
                self.document_version_id,
                self.sanitized_text,
                self.source_type,
                self.authorization_fingerprint,
            )
        ):
            raise EvidenceResolutionError("evidence packet fields are incomplete")
        for field_name in ("updated_at", "effective_at"):
            timestamp = getattr(self, field_name)
            if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(
                timestamp
            ):
                raise EvidenceResolutionError(f"{field_name} must be UTC-aware")
        if self.authority_level < 0:
            raise EvidenceResolutionError("evidence authority must not be negative")
        if self.external_shareable and self.classification not in {
            Classification.PUBLIC,
            Classification.CUSTOMER_SHAREABLE,
        }:
            raise EvidenceResolutionError(
                "classification cannot be externally shareable"
            )


@dataclass(frozen=True, slots=True)
class EvidenceConflict:
    """A preserved conflict group, not an attempted semantic reconciliation."""

    conflict_group: str
    evidence_ids: tuple[EvidenceId, ...]
    most_authoritative_evidence_id: EvidenceId

    def __post_init__(self) -> None:
        if not self.conflict_group.strip() or len(self.evidence_ids) < 2:
            raise ValueError("conflicts require a group and at least two evidence IDs")


@dataclass(frozen=True, slots=True)
class EvidenceSourceGroup:
    """Chunks from the same source revision retained as one traceable group."""

    document_id: str
    document_version_id: str
    evidence_ids: tuple[EvidenceId, ...]


@dataclass(frozen=True, slots=True)
class EvidenceResolutionTrace:
    """Content-free accounting for a single evidence resolution operation."""

    correlation_id: str
    authorization_fingerprint: str
    reranker_version: str
    input_candidate_count: int
    reauthorized_candidate_count: int
    loaded_material_count: int
    duplicate_count: int
    authorization_drop_count: int
    fallback_used: bool


@dataclass(frozen=True, slots=True)
class EvidenceResolution:
    """The complete P13 result; no answer, context, or citation claim is generated."""

    packets: tuple[EvidencePacket, ...]
    source_groups: tuple[EvidenceSourceGroup, ...]
    conflicts: tuple[EvidenceConflict, ...]
    most_relevant_evidence_id: EvidenceId | None
    most_authoritative_evidence_id: EvidenceId | None
    trace: EvidenceResolutionTrace

    def __post_init__(self) -> None:
        if any(
            packet.authorization_fingerprint != self.trace.authorization_fingerprint
            for packet in self.packets
        ):
            raise EvidenceResolutionError(
                "evidence packets must share the current authorization binding"
            )


def stable_evidence_id(chunk_id: str, document_version_id: str) -> EvidenceId:
    """Create a citation-stable ID without binding it to a user or query."""

    material = f"{chunk_id}|{document_version_id}|evidence-v1"
    return EvidenceId(f"evidence_{sha256(material.encode('utf-8')).hexdigest()[:32]}")


def policy_priority(packet: EvidencePacket) -> tuple[int, int, int, int, float, str]:
    """Rank authority without conflating it with relevance."""

    current = 1 if packet.freshness is EvidenceFreshness.CURRENT else 0
    not_superseded = 0 if packet.freshness is EvidenceFreshness.SUPERSEDED else 1
    status = {
        EvidenceDecisionStatus.COMMITTED: 3,
        EvidenceDecisionStatus.APPROVED: 2,
        EvidenceDecisionStatus.TENTATIVE: 1,
        EvidenceDecisionStatus.INFORMATIONAL: 0,
    }[packet.decision_status]
    return (
        current,
        not_superseded,
        packet.authority_level,
        status,
        packet.effective_at.timestamp(),
        str(packet.evidence_id),
    )


def rank_lookup(
    scores: Sequence[RerankScore],
) -> Mapping[EvidenceId, tuple[int, float]]:
    """Keep the first rank for each ID and reject no data silently."""

    result: dict[EvidenceId, tuple[int, float]] = {}
    for rank, score in enumerate(scores, start=1):
        result.setdefault(score.evidence_id, (rank, score.score))
    return result
