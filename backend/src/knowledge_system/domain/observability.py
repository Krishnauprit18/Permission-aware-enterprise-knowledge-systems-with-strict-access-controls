"""Content-free, typed records for operational traces and security audit."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import NewType

AuditEventId = NewType("AuditEventId", str)

_SAFE_STAGE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SAFE_ERROR = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


class AuditEventType(StrEnum):
    """Allowlisted security and lifecycle events."""

    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    AUTHZ_DECISION = "AUTHZ_DECISION"
    AUTHZ_DENIAL = "AUTHZ_DENIAL"
    ROLE_CHANGE = "ROLE_CHANGE"
    INGESTION = "INGESTION"
    DELETION = "DELETION"
    POLICY_CHANGE = "POLICY_CHANGE"
    ADMIN_ACTION = "ADMIN_ACTION"
    QUERY = "QUERY"


class AuditOutcome(StrEnum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    REFUSED = "REFUSED"
    FAILED = "FAILED"
    SUCCEEDED = "SUCCEEDED"


@dataclass(frozen=True, slots=True)
class CandidateAudit:
    """Safe ranked candidate metadata; it contains no text or vector."""

    chunk_id: str
    document_version_id: str
    lexical_rank: int | None = None
    vector_rank: int | None = None
    fused_rank: int | None = None
    rerank_rank: int | None = None
    lexical_score: float | None = None
    vector_score: float | None = None

    def __post_init__(self) -> None:
        if not self.chunk_id.strip() or not self.document_version_id.strip():
            raise ValueError("candidate audit identity is required")
        for name in (
            "lexical_rank",
            "vector_rank",
            "fused_rank",
            "rerank_rank",
        ):
            value = getattr(self, name)
            if value is not None and value < 1:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class QueryAuditRecord:
    """Minimized per-query record suitable for durable local audit storage."""

    trace_id: str
    correlation_id: str
    pseudonymous_subject_id: str
    tenant_id: str
    query_hash: str
    query_length: int
    query_term_count: int
    authorization_fingerprint: str
    authorization_model_id: str
    tuple_version: str
    policy_version: str
    authorized_scope_size: int
    candidates: tuple[CandidateAudit, ...]
    evidence_ids: tuple[str, ...]
    document_version_ids: tuple[str, ...]
    prompt_template_version: str
    model_id: str
    model_version: str
    citation_validation_result: str
    latency_ms_by_stage: Mapping[str, int]
    context_char_count: int
    input_token_count: int | None
    output_token_count: int | None
    policy_warnings: tuple[str, ...]
    outcome: AuditOutcome
    error_class: str | None
    created_at: datetime
    schema_version: str = "query-audit-v1"

    def __post_init__(self) -> None:
        required = (
            self.trace_id,
            self.correlation_id,
            self.pseudonymous_subject_id,
            self.tenant_id,
            self.query_hash,
            self.authorization_fingerprint,
            self.authorization_model_id,
            self.tuple_version,
            self.policy_version,
            self.prompt_template_version,
            self.model_id,
            self.model_version,
            self.citation_validation_result,
            self.schema_version,
        )
        if any(not value.strip() for value in required):
            raise ValueError("query audit identity is incomplete")
        if self.query_length < 1 or self.query_term_count < 0:
            raise ValueError("query audit bounds are invalid")
        if self.authorized_scope_size < 0 or self.context_char_count < 0:
            raise ValueError("query audit counts are invalid")
        for name, value in (
            ("input_token_count", self.input_token_count),
            ("output_token_count", self.output_token_count),
        ):
            if value is not None and value < 0:
                raise ValueError(f"{name} must not be negative")
        if not self.latency_ms_by_stage:
            raise ValueError("query audit latency breakdown is required")
        for stage, latency in self.latency_ms_by_stage.items():
            if not _SAFE_STAGE.fullmatch(stage) or latency < 0:
                raise ValueError("query audit latency breakdown is invalid")
        if self.error_class is not None and not _SAFE_ERROR.fullmatch(self.error_class):
            raise ValueError("query audit error class is invalid")
        if (
            self.created_at.tzinfo is None
            or self.created_at.utcoffset() != UTC.utcoffset(self.created_at)
        ):
            raise ValueError("query audit timestamp must be UTC-aware")

    def metadata_json(self) -> dict[str, object]:
        """Return a JSON-safe payload with no raw query, text, or vector."""

        return {
            "authorization_model_id": self.authorization_model_id,
            "authorized_scope_size": self.authorized_scope_size,
            "candidates": [
                {
                    "chunk_id": item.chunk_id,
                    "document_version_id": item.document_version_id,
                    "fused_rank": item.fused_rank,
                    "lexical_rank": item.lexical_rank,
                    "lexical_score": item.lexical_score,
                    "rerank_rank": item.rerank_rank,
                    "vector_rank": item.vector_rank,
                    "vector_score": item.vector_score,
                }
                for item in self.candidates
            ],
            "citation_validation_result": self.citation_validation_result,
            "context_char_count": self.context_char_count,
            "document_version_ids": list(self.document_version_ids),
            "error_class": self.error_class,
            "input_token_count": self.input_token_count,
            "latency_ms_by_stage": dict(self.latency_ms_by_stage),
            "model_id": self.model_id,
            "model_version": self.model_version,
            "output_token_count": self.output_token_count,
            "policy_warnings": list(self.policy_warnings),
            "prompt_template_version": self.prompt_template_version,
            "query_length": self.query_length,
            "query_term_count": self.query_term_count,
            "schema_version": self.schema_version,
            "tuple_version": self.tuple_version,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class SecurityAuditEvent:
    """A minimized security event with an allowlisted event category."""

    event_id: AuditEventId
    event_type: AuditEventType
    correlation_id: str
    trace_id: str | None
    pseudonymous_subject_id: str | None
    tenant_id: str | None
    outcome: AuditOutcome
    reason_code: str
    target_ref_hash: str | None
    attributes: Mapping[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    schema_version: str = "security-audit-v1"

    def __post_init__(self) -> None:
        if not str(self.event_id).strip() or not self.correlation_id.strip():
            raise ValueError("audit event identity is required")
        if not self.reason_code.strip() or len(self.reason_code) > 64:
            raise ValueError("audit reason code is invalid")
        if (
            self.created_at.tzinfo is None
            or self.created_at.utcoffset() != UTC.utcoffset(self.created_at)
        ):
            raise ValueError("audit event timestamp must be UTC-aware")
        if any(not key.strip() or len(key) > 64 for key in self.attributes):
            raise ValueError("audit attributes must have bounded keys")


def pseudonymous_subject_id(subject_id: str, *, namespace: str = "local") -> str:
    """Create a stable non-reversible subject reference for telemetry."""

    normalized = unicodedata.normalize("NFC", subject_id.strip())
    if not normalized or not namespace.strip():
        raise ValueError("subject and namespace are required")
    return sha256(f"{namespace}:{normalized}".encode()).hexdigest()


def normalized_query_metadata(question: str) -> tuple[str, int, int]:
    """Return query hash, character count, and term count without retaining text."""

    normalized = " ".join(unicodedata.normalize("NFC", question).split())
    if not normalized:
        raise ValueError("query must not be empty")
    return (
        sha256(normalized.casefold().encode("utf-8")).hexdigest(),
        len(normalized),
        len(normalized.split()),
    )
