"""Application-owned constructors for safe lifecycle audit events."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256

from knowledge_system.domain.observability import (
    AuditEventId,
    AuditEventType,
    AuditOutcome,
    SecurityAuditEvent,
    pseudonymous_subject_id,
)


def lifecycle_event(
    event_type: AuditEventType,
    *,
    correlation_id: str,
    outcome: AuditOutcome,
    reason_code: str,
    tenant_id: str | None = None,
    subject_id: str | None = None,
    target_ref: str | None = None,
    attributes: Mapping[str, object] | None = None,
) -> SecurityAuditEvent:
    """Create a stable, non-content event for lifecycle or policy work."""

    target_ref_hash = (
        sha256(target_ref.encode("utf-8")).hexdigest() if target_ref else None
    )
    material = f"{event_type.value}:{correlation_id}:{target_ref_hash}:{reason_code}"
    return SecurityAuditEvent(
        event_id=AuditEventId("audit_" + sha256(material.encode()).hexdigest()),
        event_type=event_type,
        correlation_id=correlation_id,
        trace_id=correlation_id,
        pseudonymous_subject_id=(
            pseudonymous_subject_id(subject_id) if subject_id else None
        ),
        tenant_id=tenant_id,
        outcome=outcome,
        reason_code=reason_code[:64],
        target_ref_hash=target_ref_hash,
        attributes=dict(attributes or {}),
    )
