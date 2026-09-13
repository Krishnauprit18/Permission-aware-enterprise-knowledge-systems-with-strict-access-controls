"""Small, framework-independent contracts used to protect authorization flow."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, NewType

AuthorizedObjectId = NewType("AuthorizedObjectId", str)
PrincipalId = NewType("PrincipalId", str)
EvidenceId = NewType("EvidenceId", str)
AuthorizationRelation = Literal["can_view", "can_share_externally"]


class AuthorizationOutcome(StrEnum):
    """Auditable outcomes; only ALLOW can cross a protected boundary."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True, slots=True)
class PrincipalContext:
    """Validated identity metadata; authorization remains an external decision."""

    subject_id: PrincipalId
    tenant_id: str
    groups: tuple[str, ...] = ()
    claims: Mapping[str, object] = field(default_factory=dict)
    correlation_id: str = ""

    @property
    def principal_id(self) -> PrincipalId:
        """Compatibility alias for the subject identifier."""

        return self.subject_id


@dataclass(frozen=True, slots=True)
class CandidateEnvelope:
    """Metadata-only search candidate; it deliberately carries no searchable text."""

    object_id: AuthorizedObjectId
    tenant_id: str
    source: str
    access_level: str
    chunk_id: str = ""
    document_id: str = ""
    document_version_id: str = ""
    lexical_score: float | None = None
    vector_score: float | None = None
    provenance: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AuthorizedChunk:
    """Text is represented only after an authorization service returns an object ID."""

    object_id: AuthorizedObjectId
    evidence_id: EvidenceId
    text: str
    tenant_id: str


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    """Explicit authorization result; absence of authorization is never implicit allow."""

    allowed: bool
    can_share_externally: bool = False
    outcome: AuthorizationOutcome | None = None
    reason_code: str = "unspecified"
    authorization_model_id: str = "unknown"
    tuple_version: str = "unknown"
    policy_version: str = "policy-v1"
    decision_fingerprint: str = ""
    correlation_id: str = ""

    def __post_init__(self) -> None:
        if self.can_share_externally and not self.allowed:
            raise ValueError("external sharing requires view authorization")
        if self.outcome is None:
            object.__setattr__(
                self,
                "outcome",
                AuthorizationOutcome.ALLOW
                if self.allowed
                else AuthorizationOutcome.DENY,
            )
        if self.allowed and self.outcome is not AuthorizationOutcome.ALLOW:
            raise ValueError("allowed decisions must have ALLOW outcome")
        if not self.allowed and self.outcome is AuthorizationOutcome.ALLOW:
            raise ValueError("denied decisions cannot have ALLOW outcome")
