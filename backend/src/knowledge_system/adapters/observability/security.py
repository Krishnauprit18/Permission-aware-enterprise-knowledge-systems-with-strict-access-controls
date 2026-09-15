"""Bridge OpenFGA decisions to minimized security audit events."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256

from knowledge_system.adapters.observability.redaction import RedactedAuditLogger
from knowledge_system.application.ports.authorization import (
    AuthorizationDecisionAuditSink,
)
from knowledge_system.application.ports.observability import SecurityAuditSink
from knowledge_system.domain.contracts import (
    AuthorizationDecision,
    AuthorizedObjectId,
    PrincipalContext,
)
from knowledge_system.domain.observability import (
    AuditEventId,
    AuditEventType,
    AuditOutcome,
    SecurityAuditEvent,
    pseudonymous_subject_id,
)


@dataclass(slots=True)
class AuthorizationAuditBridge(AuthorizationDecisionAuditSink):
    """Translate safe OpenFGA decisions to the durable security-event port."""

    sink: SecurityAuditSink
    logger: RedactedAuditLogger | None = None

    def record_authorization_decision(
        self,
        decision: AuthorizationDecision,
        *,
        principal: PrincipalContext,
        object_id: AuthorizedObjectId | None,
        attributes: Mapping[str, str],
    ) -> None:
        event = SecurityAuditEvent(
            event_id=AuditEventId(
                "audit_"
                + sha256(
                    f"authz:{principal.correlation_id}:{object_id}:{decision.reason_code}".encode()
                ).hexdigest()
            ),
            event_type=(
                AuditEventType.AUTHZ_DECISION
                if decision.allowed
                else AuditEventType.AUTHZ_DENIAL
            ),
            correlation_id=principal.correlation_id,
            trace_id=principal.correlation_id,
            pseudonymous_subject_id=pseudonymous_subject_id(str(principal.subject_id)),
            tenant_id=principal.tenant_id,
            outcome=(AuditOutcome.ALLOWED if decision.allowed else AuditOutcome.DENIED),
            reason_code=decision.reason_code[:64],
            target_ref_hash=(
                sha256(str(object_id).encode()).hexdigest()
                if object_id is not None
                else None
            ),
            attributes=dict(attributes),
        )
        self.sink.record_security_event(event)
        if self.logger is not None:
            self.logger.security_event(event)
