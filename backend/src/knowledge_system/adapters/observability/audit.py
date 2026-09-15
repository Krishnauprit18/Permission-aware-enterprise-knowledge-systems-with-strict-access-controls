"""Durable local PostgreSQL sink for minimized query and security audit."""

from dataclasses import dataclass
from hashlib import sha256

from knowledge_system.application.ports.observability import (
    QueryAuditSink,
    SecurityAuditSink,
)
from knowledge_system.application.ports.persistence import UnitOfWorkFactory
from knowledge_system.domain.observability import (
    AuditEventId,
    AuditEventType,
    QueryAuditRecord,
    SecurityAuditEvent,
)


@dataclass(slots=True)
class PostgresAuditSink(QueryAuditSink, SecurityAuditSink):
    """Persist content-free audit records in the canonical local database."""

    unit_of_work: UnitOfWorkFactory

    def record_query(self, record: QueryAuditRecord) -> None:
        event = SecurityAuditEvent(
            event_id=AuditEventId(
                "audit_" + sha256(f"query:{record.trace_id}".encode()).hexdigest()
            ),
            event_type=AuditEventType.QUERY,
            correlation_id=record.correlation_id,
            trace_id=record.trace_id,
            pseudonymous_subject_id=record.pseudonymous_subject_id,
            tenant_id=record.tenant_id,
            outcome=record.outcome,
            reason_code="query_completed",
            target_ref_hash=record.query_hash,
            attributes=record.metadata_json(),
            created_at=record.created_at,
        )
        self.record_security_event(event)

    def record_security_event(self, event: SecurityAuditEvent) -> None:
        with self.unit_of_work() as repository:
            repository.save_security_audit_event(event)
