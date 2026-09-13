"""Authentication use cases with generic client failures and explicit revocation."""

from dataclasses import dataclass
from time import time

from knowledge_system.application.ports.authentication import (
    IdentityTokenValidator,
    SessionRevocationStore,
    ValidatedIdentity,
)


class AuthenticationFailure(Exception):
    """Internal authentication failure; callers must expose a generic response."""


@dataclass(slots=True)
class InMemorySessionRevocationStore:
    """Small local-only revocation store until durable session state is introduced."""

    _revoked: dict[str, int]

    def __init__(self) -> None:
        self._revoked = {}

    def revoke(self, session_id: str, *, expires_at: int) -> None:
        self._revoked[session_id] = expires_at

    def is_revoked(self, session_id: str, *, now: int) -> bool:
        expiry = self._revoked.get(session_id)
        if expiry is None:
            return False
        if expiry <= now:
            del self._revoked[session_id]
            return False
        return True


class AuthenticationService:
    """Coordinate token validation and server-side session invalidation."""

    def __init__(
        self,
        validator: IdentityTokenValidator,
        revocations: SessionRevocationStore,
    ) -> None:
        self._validator = validator
        self._revocations = revocations

    def authenticate(
        self, bearer_token: str, *, correlation_id: str
    ) -> ValidatedIdentity:
        if not bearer_token.strip():
            raise AuthenticationFailure
        try:
            identity = self._validator.validate(
                bearer_token, correlation_id=correlation_id
            )
        except Exception as exc:
            raise AuthenticationFailure from exc
        if self._revocations.is_revoked(identity.session_id, now=int(time())):
            raise AuthenticationFailure
        return identity

    def logout(self, bearer_token: str, *, correlation_id: str) -> None:
        identity = self.authenticate(bearer_token, correlation_id=correlation_id)
        self._revocations.revoke(
            identity.session_id,
            expires_at=identity.expires_at,
        )
