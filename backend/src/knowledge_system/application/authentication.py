"""Authentication use cases with generic client failures and explicit revocation."""

import logging
from dataclasses import dataclass
from time import time

from knowledge_system.application.audit import lifecycle_event
from knowledge_system.application.ports.authentication import (
    IdentityTokenValidator,
    SessionRevocationStore,
    ValidatedIdentity,
)
from knowledge_system.application.ports.observability import (
    AuditLogger,
    SecurityAuditSink,
)
from knowledge_system.domain.observability import AuditEventType, AuditOutcome


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
        *,
        audit_sink: SecurityAuditSink | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self._validator = validator
        self._revocations = revocations
        self._audit_sink = audit_sink
        self._audit_logger = audit_logger

    def authenticate(
        self, bearer_token: str, *, correlation_id: str
    ) -> ValidatedIdentity:
        if not bearer_token.strip():
            self._emit_login(correlation_id, AuditOutcome.FAILED, "missing_token")
            raise AuthenticationFailure
        try:
            identity = self._validator.validate(
                bearer_token, correlation_id=correlation_id
            )
        except Exception as exc:
            self._emit_login(
                correlation_id, AuditOutcome.FAILED, "authentication_failed"
            )
            raise AuthenticationFailure from exc
        if self._revocations.is_revoked(identity.session_id, now=int(time())):
            self._emit_login(
                correlation_id,
                AuditOutcome.DENIED,
                "session_revoked",
                identity,
            )
            raise AuthenticationFailure
        self._emit_login(
            correlation_id, AuditOutcome.ALLOWED, "authenticated", identity
        )
        return identity

    def logout(self, bearer_token: str, *, correlation_id: str) -> None:
        identity = self.authenticate(bearer_token, correlation_id=correlation_id)
        self._revocations.revoke(
            identity.session_id,
            expires_at=identity.expires_at,
        )
        self._emit_login(
            correlation_id,
            AuditOutcome.SUCCEEDED,
            "logout_completed",
            identity,
            event_type=AuditEventType.LOGOUT,
        )

    def _emit_login(
        self,
        correlation_id: str,
        outcome: AuditOutcome,
        reason_code: str,
        identity: ValidatedIdentity | None = None,
        *,
        event_type: AuditEventType = AuditEventType.LOGIN,
    ) -> None:
        if self._audit_sink is None and self._audit_logger is None:
            return
        event = lifecycle_event(
            event_type,
            correlation_id=correlation_id,
            outcome=outcome,
            reason_code=reason_code,
            tenant_id=identity.principal.tenant_id if identity else None,
            subject_id=str(identity.principal.subject_id) if identity else None,
            target_ref=identity.session_id if identity else None,
        )
        if self._audit_sink is not None:
            try:
                self._audit_sink.record_security_event(event)
            except (OSError, RuntimeError, ValueError):
                logging.getLogger(__name__).warning(
                    "security_audit_write_failed",
                    extra={
                        "correlation_id": correlation_id,
                        "event_type": event_type.value,
                    },
                )
        if self._audit_logger is not None:
            try:
                self._audit_logger.security_event(event)
            except (OSError, RuntimeError, ValueError):
                logging.getLogger(__name__).warning(
                    "security_audit_log_failed",
                    extra={
                        "correlation_id": correlation_id,
                        "event_type": event_type.value,
                    },
                )
