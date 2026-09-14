"""Typed contracts for grounded, citation-validated answer generation."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256

from knowledge_system.domain.contracts import EvidenceId
from knowledge_system.domain.evidence import (
    EvidenceAnnotation,
    EvidenceConflict,
    EvidenceDecisionStatus,
    EvidenceFreshness,
)
from knowledge_system.domain.persistence import Classification


class GenerationContractError(ValueError):
    """A model-facing or user-facing generation contract is malformed."""


class CitationValidationError(GenerationContractError):
    """A model draft references evidence outside its supplied context."""


class GenerationOutcome(StrEnum):
    """Safe, user-visible result classes for the answer boundary."""

    ANSWERED = "ANSWERED"
    REFUSED = "REFUSED"
    UNAVAILABLE = "UNAVAILABLE"


class CitationValidationStatus(StrEnum):
    """Content-free citation-validation state retained in audit traces."""

    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    VALID = "VALID"
    RETRIED_VALID = "RETRIED_VALID"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class PromptDefinition:
    """An immutable trusted prompt definition without retrieved content."""

    purpose: str
    version: str
    instructions: str

    def __post_init__(self) -> None:
        if not all(
            value.strip() for value in (self.purpose, self.version, self.instructions)
        ):
            raise GenerationContractError("prompt definition fields are required")

    @property
    def content_hash(self) -> str:
        return sha256(self.instructions.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ContextEvidence:
    """A selected authorized evidence item represented as untrusted model data."""

    evidence_id: EvidenceId
    text: str
    source_type: str
    decision_status: EvidenceDecisionStatus
    freshness: EvidenceFreshness
    authority_level: int
    annotations: tuple[EvidenceAnnotation, ...]

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (str(self.evidence_id), self.text, self.source_type)
        ):
            raise GenerationContractError("context evidence fields are required")
        if self.authority_level < 0:
            raise GenerationContractError("context evidence authority is invalid")


@dataclass(frozen=True, slots=True)
class AuthorizedGenerationContext:
    """The only text-bearing context accepted by the grounded model port."""

    question: str
    evidence: tuple[ContextEvidence, ...]
    conflicts: tuple[EvidenceConflict, ...]
    authorization_fingerprint: str
    correlation_id: str
    prompt: PromptDefinition
    context_char_count: int

    def __post_init__(self) -> None:
        if not 1 <= len(self.question.strip()) <= 2_000:
            raise GenerationContractError(
                "generation question is outside the allowed bound"
            )
        if (
            not self.authorization_fingerprint.strip()
            or not self.correlation_id.strip()
        ):
            raise GenerationContractError(
                "generation authorization context is required"
            )
        if self.context_char_count != sum(len(item.text) for item in self.evidence):
            raise GenerationContractError("generation context size is inconsistent")
        evidence_ids = tuple(item.evidence_id for item in self.evidence)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise GenerationContractError(
                "generation context evidence IDs must be unique"
            )
        allowed_ids = set(evidence_ids)
        if any(
            not set(conflict.evidence_ids).issubset(allowed_ids)
            for conflict in self.conflicts
        ):
            raise GenerationContractError(
                "generation conflict references omitted evidence"
            )

    @property
    def evidence_ids(self) -> tuple[EvidenceId, ...]:
        return tuple(item.evidence_id for item in self.evidence)

    def evidence_data_json(self) -> str:
        """Serialize evidence deterministically for a data-only model message."""

        payload = [
            {
                "annotations": [annotation.value for annotation in item.annotations],
                "authority_level": item.authority_level,
                "decision_status": item.decision_status.value,
                "evidence_id": str(item.evidence_id),
                "freshness": item.freshness.value,
                "source_type": item.source_type,
                "text": item.text,
            }
            for item in self.evidence
        ]
        return json.dumps(
            payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        )


@dataclass(frozen=True, slots=True)
class CitationProposal:
    """A model proposal limited to an evidence ID and verbatim supporting quote."""

    evidence_id: EvidenceId
    quote: str

    def __post_init__(self) -> None:
        if not str(self.evidence_id).strip() or not 1 <= len(self.quote.strip()) <= 500:
            raise GenerationContractError("citation proposal is invalid")


@dataclass(frozen=True, slots=True)
class ModelClaim:
    """One structured factual answer claim; every claim needs a citation proposal."""

    text: str
    citations: tuple[CitationProposal, ...]

    def __post_init__(self) -> None:
        if not 1 <= len(self.text.strip()) <= 1_200 or not self.citations:
            raise GenerationContractError("model claim must be bounded and cited")
        if len(self.citations) > 8:
            raise GenerationContractError("model claim has too many citations")


@dataclass(frozen=True, slots=True)
class ModelDraft:
    """Schema-first local-model output before deterministic validation."""

    claims: tuple[ModelClaim, ...] = ()
    insufficient_evidence: bool = False

    def __post_init__(self) -> None:
        if len(self.claims) > 12:
            raise GenerationContractError("model draft has too many claims")
        if self.insufficient_evidence and self.claims:
            raise GenerationContractError("refusal draft cannot contain factual claims")
        if not self.insufficient_evidence and not self.claims:
            raise GenerationContractError("answer draft must contain cited claims")


@dataclass(frozen=True, slots=True)
class ValidatedCitation:
    """Citation display metadata constructed only from backend evidence packets."""

    evidence_id: EvidenceId
    quote: str
    source_type: str
    source_locator: tuple[str, ...]
    source_url: str | None
    updated_at: datetime
    classification: Classification

    def __post_init__(self) -> None:
        if not str(self.evidence_id).strip() or not self.quote.strip():
            raise GenerationContractError("validated citation identity is required")
        if (
            self.updated_at.tzinfo is None
            or self.updated_at.utcoffset() != UTC.utcoffset(self.updated_at)
        ):
            raise GenerationContractError("citation timestamp must be UTC-aware")


@dataclass(frozen=True, slots=True)
class GroundedClaim:
    """A validated factual statement with backend-renderable citations."""

    text: str
    citations: tuple[ValidatedCitation, ...]

    def __post_init__(self) -> None:
        if not self.text.strip() or not self.citations:
            raise GenerationContractError("grounded claim must contain citations")


@dataclass(frozen=True, slots=True)
class ConflictNotice:
    """Backend-derived conflict disclosure; it is never invented by the model."""

    evidence_ids: tuple[EvidenceId, ...]
    most_authoritative_evidence_id: EvidenceId


@dataclass(frozen=True, slots=True)
class EvidenceQualification:
    """Trusted freshness/status qualification available to the answer renderer."""

    evidence_id: EvidenceId
    decision_status: EvidenceDecisionStatus
    freshness: EvidenceFreshness


@dataclass(frozen=True, slots=True)
class GenerationTrace:
    """Content-free audit metadata for one bounded generation attempt sequence."""

    correlation_id: str
    authorization_fingerprint: str
    prompt_purpose: str
    prompt_version: str
    prompt_hash: str
    model_id: str
    model_version: str
    evidence_ids: tuple[EvidenceId, ...]
    context_char_count: int
    attempts: int
    citation_validation: CitationValidationStatus
    outcome: GenerationOutcome
    latency_ms: int
    created_at: datetime

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.correlation_id,
                self.authorization_fingerprint,
                self.prompt_purpose,
                self.prompt_version,
                self.prompt_hash,
                self.model_id,
                self.model_version,
            )
        ):
            raise GenerationContractError("generation trace identity is required")
        if self.context_char_count < 0 or self.attempts < 0 or self.latency_ms < 0:
            raise GenerationContractError("generation trace bounds are invalid")
        if (
            self.created_at.tzinfo is None
            or self.created_at.utcoffset() != UTC.utcoffset(self.created_at)
        ):
            raise GenerationContractError(
                "generation trace timestamp must be UTC-aware"
            )


@dataclass(frozen=True, slots=True)
class GroundedAnswer:
    """Safe answer response with backend-controlled citations and trace metadata."""

    outcome: GenerationOutcome
    message: str
    claims: tuple[GroundedClaim, ...]
    conflicts: tuple[ConflictNotice, ...]
    qualifications: tuple[EvidenceQualification, ...]
    trace: GenerationTrace

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise GenerationContractError("generation response message is required")
        if self.outcome is GenerationOutcome.ANSWERED and not self.claims:
            raise GenerationContractError("answered response requires grounded claims")
        if self.outcome is not GenerationOutcome.ANSWERED and self.claims:
            raise GenerationContractError("non-answer response cannot contain claims")


def conflict_notices(
    conflicts: Sequence[EvidenceConflict],
) -> tuple[ConflictNotice, ...]:
    """Project resolved conflict metadata into a renderer-safe response shape."""

    return tuple(
        ConflictNotice(
            evidence_ids=conflict.evidence_ids,
            most_authoritative_evidence_id=conflict.most_authoritative_evidence_id,
        )
        for conflict in conflicts
    )
