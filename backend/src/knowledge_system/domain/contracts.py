"""Small, framework-independent contracts used to protect authorization flow."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import NewType

AuthorizedObjectId = NewType("AuthorizedObjectId", str)
PrincipalId = NewType("PrincipalId", str)
EvidenceId = NewType("EvidenceId", str)


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

    def __post_init__(self) -> None:
        if self.can_share_externally and not self.allowed:
            raise ValueError("external sharing requires view authorization")
