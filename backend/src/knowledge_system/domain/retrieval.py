"""Typed, text-free contracts for permission-first hybrid retrieval."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from typing import Protocol

from knowledge_system.domain.contracts import (
    AuthorizationDecision,
    AuthorizedObjectId,
    CandidateEnvelope,
    PrincipalContext,
)


class RetrievalInputError(ValueError):
    """A query or narrowing filter violates a deterministic request bound."""


class RetrievalAuthorizationError(RuntimeError):
    """The protected retrieval path could not establish current authorization."""


_SAFE_FILTER_VALUE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")


class AuthorizationScopeLike(Protocol):
    """Structural view of a scope that keeps the domain free of application imports."""

    @property
    def tenant_id(self) -> str: ...

    @property
    def resource_ids(self) -> tuple[AuthorizedObjectId, ...]: ...

    @property
    def authorization_model_id(self) -> str: ...

    @property
    def tuple_version(self) -> str: ...

    @property
    def policy_version(self) -> str: ...

    @property
    def decision_fingerprint(self) -> str: ...


@dataclass(frozen=True, slots=True)
class RequestedQueryFilters:
    """User constraints that may only narrow a server-owned authorization scope."""

    account_ids: tuple[str, ...] = ()
    department: str | None = None
    updated_after: datetime | None = None
    updated_before: datetime | None = None

    def __post_init__(self) -> None:
        if len(self.account_ids) > 20 or len(set(self.account_ids)) != len(
            self.account_ids
        ):
            raise RetrievalInputError("too many or duplicate account filters")
        if any(not _SAFE_FILTER_VALUE.fullmatch(value) for value in self.account_ids):
            raise RetrievalInputError("account filters contain an invalid value")
        if self.department is not None and not _SAFE_FILTER_VALUE.fullmatch(
            self.department
        ):
            raise RetrievalInputError("department filter contains an invalid value")
        for value in (self.updated_after, self.updated_before):
            if value is not None and (
                value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
            ):
                raise RetrievalInputError("date filters must be UTC-aware")
        if (
            self.updated_after is not None
            and self.updated_before is not None
            and self.updated_after > self.updated_before
        ):
            raise RetrievalInputError("date filter range is invalid")


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    """Bounded user query; it contains no raw OpenSearch DSL."""

    question: str
    filters: RequestedQueryFilters = field(default_factory=RequestedQueryFilters)
    result_limit: int = 20
    component_limit: int = 50

    def __post_init__(self) -> None:
        if not 1 <= len(self.question.strip()) <= 2_000:
            raise RetrievalInputError("query length is outside the allowed bound")
        if not 1 <= self.result_limit <= 50 or not 1 <= self.component_limit <= 100:
            raise RetrievalInputError("retrieval limits are outside the allowed bound")


@dataclass(frozen=True, slots=True)
class AuthorizationFilter:
    """Immutable server-generated authorization constraint for one request."""

    tenant_id: str
    resource_ids: tuple[AuthorizedObjectId, ...]
    authorization_model_id: str
    tuple_version: str
    policy_version: str
    decision_fingerprint: str

    @classmethod
    def from_scope(
        cls, principal: PrincipalContext, scope: AuthorizationScopeLike
    ) -> AuthorizationFilter:
        if scope.tenant_id != principal.tenant_id:
            raise RetrievalAuthorizationError("authorization scope unavailable")
        if any(
            not value.strip()
            for value in (
                scope.authorization_model_id,
                scope.tuple_version,
                scope.policy_version,
                scope.decision_fingerprint,
            )
        ):
            raise RetrievalAuthorizationError("authorization scope unavailable")
        resource_ids = tuple(sorted(set(scope.resource_ids), key=str))
        if any(
            not str(resource_id).startswith("resource:")
            or len(str(resource_id)) <= len("resource:")
            for resource_id in resource_ids
        ):
            raise RetrievalAuthorizationError("authorization scope unavailable")
        return cls(
            tenant_id=scope.tenant_id,
            resource_ids=resource_ids,
            authorization_model_id=scope.authorization_model_id,
            tuple_version=scope.tuple_version,
            policy_version=scope.policy_version,
            decision_fingerprint=scope.decision_fingerprint,
        )

    @property
    def document_ids(self) -> tuple[str, ...]:
        """Translate trusted OpenFGA resource refs to canonical index document IDs."""

        return tuple(
            str(resource_id).removeprefix("resource:")
            for resource_id in self.resource_ids
        )


@dataclass(frozen=True, slots=True)
class EffectiveSearchFilter:
    """The only filter object accepted by the P12 search adapter."""

    authorization: AuthorizationFilter
    account_ids: tuple[str, ...] = ()
    department: str | None = None
    updated_after: datetime | None = None
    updated_before: datetime | None = None

    @classmethod
    def intersect(
        cls, authorization: AuthorizationFilter, requested: RequestedQueryFilters
    ) -> EffectiveSearchFilter:
        return cls(
            authorization=authorization,
            account_ids=tuple(sorted(requested.account_ids)),
            department=requested.department,
            updated_after=requested.updated_after,
            updated_before=requested.updated_before,
        )

    @property
    def has_authorized_resources(self) -> bool:
        return bool(self.authorization.resource_ids)


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    """Authorized metadata-only candidate; text is intentionally absent."""

    chunk_id: str
    resource_id: AuthorizedObjectId
    tenant_id: str
    source_type: str
    source_external_id: str
    document_id: str
    document_version_id: str
    classification: str
    account_ids: tuple[str, ...]
    department: str
    citation_locators: tuple[str, ...]
    updated_at: datetime
    authorization: AuthorizationDecision
    provenance: Mapping[str, str] = field(default_factory=dict)
    external_shareable: bool = False

    def __post_init__(self) -> None:
        if (
            not self.chunk_id.strip()
            or not self.source_type.strip()
            or not self.document_id.strip()
        ):
            raise RetrievalInputError("candidate provenance is incomplete")
        if not self.authorization.allowed:
            raise RetrievalAuthorizationError(
                "unauthorized candidate cannot cross boundary"
            )
        if (
            self.updated_at.tzinfo is None
            or self.updated_at.utcoffset() != UTC.utcoffset(self.updated_at)
        ):
            raise RetrievalInputError("candidate timestamp must be UTC-aware")


@dataclass(frozen=True, slots=True)
class ComponentDiagnostic:
    """Internal evaluation/trace data; never a user-facing answer field."""

    chunk_id: str
    lexical_rank: int | None
    vector_rank: int | None
    lexical_score: float | None
    vector_score: float | None
    fused_score: float


@dataclass(frozen=True, slots=True)
class RetrievalTrace:
    """Minimized trace metadata for retrieval evaluation and audit correlation."""

    correlation_id: str
    authorization_fingerprint: str
    authorized_scope_size: int
    coarse_candidate_count: int
    denied_candidate_count: int
    returned_candidate_count: int
    unauthorized_context_count: int
    component_diagnostics: tuple[ComponentDiagnostic, ...] = ()

    @property
    def unauthorized_context_rate(self) -> float:
        denominator = self.returned_candidate_count
        return (
            0.0 if denominator == 0 else self.unauthorized_context_count / denominator
        )


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """Candidate output for later reranking; no text-bearing context is produced."""

    candidates: tuple[RetrievalCandidate, ...]
    trace: RetrievalTrace

    def evaluation_record(self) -> RetrievalEvaluationRecord:
        """Expose ranked IDs and trace metrics without exposing source text."""

        return RetrievalEvaluationRecord(
            ranked_chunk_ids=tuple(candidate.chunk_id for candidate in self.candidates),
            ranked_resource_ids=tuple(
                str(candidate.resource_id) for candidate in self.candidates
            ),
            unauthorized_context_rate=self.trace.unauthorized_context_rate,
            authorization_fingerprint=self.trace.authorization_fingerprint,
            component_diagnostics=self.trace.component_diagnostics,
        )


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationRecord:
    """Retrieval-only evaluation hook; it deliberately has no question or text."""

    ranked_chunk_ids: tuple[str, ...]
    ranked_resource_ids: tuple[str, ...]
    unauthorized_context_rate: float
    authorization_fingerprint: str
    component_diagnostics: tuple[ComponentDiagnostic, ...]


def candidate_from_envelope(
    envelope: CandidateEnvelope,
    decision: AuthorizationDecision,
) -> RetrievalCandidate:
    """Convert a metadata-only hit after an explicit current allow decision."""

    provenance = envelope.provenance
    updated_at_value = provenance.get("updated_at")
    if updated_at_value is None:
        raise RetrievalInputError("candidate timestamp is missing")
    try:
        updated_at = datetime.fromisoformat(updated_at_value)
    except ValueError as exc:
        raise RetrievalInputError("candidate timestamp is invalid") from exc
    if updated_at.tzinfo is None:
        raise RetrievalInputError("candidate timestamp is not UTC-aware")
    return RetrievalCandidate(
        chunk_id=envelope.chunk_id,
        resource_id=envelope.object_id,
        tenant_id=envelope.tenant_id,
        source_type=envelope.source,
        source_external_id=provenance.get("source_external_id", envelope.document_id),
        document_id=envelope.document_id,
        document_version_id=envelope.document_version_id,
        classification=envelope.access_level,
        account_ids=tuple(
            value for value in provenance.get("account_ids", "").split(",") if value
        ),
        department=provenance.get("department", ""),
        citation_locators=tuple(
            value
            for value in provenance.get("citation_locators", "").split("\x1f")
            if value
        ),
        updated_at=updated_at.astimezone(UTC),
        authorization=decision,
        provenance=provenance,
        external_shareable=provenance.get("external_shareable", "false").lower()
        == "true",
    )


def fuse_rrf(
    lexical: Sequence[CandidateEnvelope],
    vector: Sequence[CandidateEnvelope],
    *,
    limit: int,
    rrf_k: int = 60,
) -> tuple[tuple[CandidateEnvelope, ...], tuple[ComponentDiagnostic, ...]]:
    """Fuse two deterministic ranked lists without inspecting chunk text."""

    if not 1 <= limit <= 100 or rrf_k < 1:
        raise RetrievalInputError("fusion bounds are invalid")
    by_chunk: dict[str, CandidateEnvelope] = {}
    ranks: dict[str, dict[str, object]] = {}
    for component, values in (("lexical", lexical), ("vector", vector)):
        for rank, candidate in enumerate(values, start=1):
            if not candidate.chunk_id.strip():
                continue
            by_chunk.setdefault(candidate.chunk_id, candidate)
            state = ranks.setdefault(candidate.chunk_id, {})
            state[f"{component}_rank"] = rank
            state[f"{component}_score"] = (
                candidate.lexical_score
                if component == "lexical"
                else candidate.vector_score
            )
    scored = []
    for chunk_id, candidate in by_chunk.items():
        state = ranks[chunk_id]
        fused = 0.0
        for component in ("lexical", "vector"):
            component_rank = state.get(f"{component}_rank")
            if isinstance(component_rank, int):
                fused += 1.0 / (rrf_k + component_rank)
        if not isfinite(fused):
            raise RetrievalInputError("fusion score is invalid")
        scored.append((fused, chunk_id, candidate, state))
    scored.sort(key=lambda item: (-item[0], item[1]))
    selected = scored[:limit]
    diagnostics = tuple(
        ComponentDiagnostic(
            chunk_id=chunk_id,
            lexical_rank=cast_int(state.get("lexical_rank")),
            vector_rank=cast_int(state.get("vector_rank")),
            lexical_score=cast_float(state.get("lexical_score")),
            vector_score=cast_float(state.get("vector_score")),
            fused_score=fused,
        )
        for fused, chunk_id, _candidate, state in selected
    )
    return (
        tuple(candidate for _fused, _chunk_id, candidate, _state in selected),
        diagnostics,
    )


def cast_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def cast_float(value: object) -> float | None:
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else None
    )
