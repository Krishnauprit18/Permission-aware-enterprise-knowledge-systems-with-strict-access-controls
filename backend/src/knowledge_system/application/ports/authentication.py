"""Framework-independent authentication ports and validated identity types."""

from dataclasses import dataclass
from typing import Protocol

from knowledge_system.domain.contracts import PrincipalContext


@dataclass(frozen=True, slots=True)
class ValidatedIdentity:
    """A validated OIDC identity with no bearer token retained in the object."""

    principal: PrincipalContext
    session_id: str
    expires_at: int


class IdentityTokenValidator(Protocol):
    """Validate a bearer token and return only a server-owned identity object."""

    def validate(
        self, bearer_token: str, *, correlation_id: str
    ) -> ValidatedIdentity: ...


class SessionRevocationStore(Protocol):
    """Store session revocations until the corresponding token expires."""

    def revoke(self, session_id: str, *, expires_at: int) -> None: ...

    def is_revoked(self, session_id: str, *, now: int) -> bool: ...
