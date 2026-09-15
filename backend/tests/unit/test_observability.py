"""P17 redaction, event, and local telemetry contract tests."""

from collections.abc import Mapping
from contextlib import AbstractContextManager
from datetime import UTC, datetime

import pytest

from knowledge_system.adapters.observability.redaction import (
    query_log_fields,
    redact_mapping,
)
from knowledge_system.adapters.observability.security import AuthorizationAuditBridge
from knowledge_system.application.audit import lifecycle_event
from knowledge_system.application.authentication import (
    AuthenticationService,
    InMemorySessionRevocationStore,
)
from knowledge_system.application.ports.authentication import ValidatedIdentity
from knowledge_system.application.ports.observability import (
    BestEffortTelemetry,
    Span,
    TelemetryValue,
)
from knowledge_system.domain.contracts import (
    AuthorizationDecision,
    AuthorizedObjectId,
    PrincipalContext,
    PrincipalId,
)
from knowledge_system.domain.observability import (
    AuditEventId,
    AuditEventType,
    AuditOutcome,
    CandidateAudit,
    QueryAuditRecord,
    SecurityAuditEvent,
)


def _record() -> QueryAuditRecord:
    return QueryAuditRecord(
        trace_id="trace-p17",
        correlation_id="corr-p17",
        pseudonymous_subject_id="subject-hash",
        tenant_id="northstar",
        query_hash="a" * 64,
        query_length=21,
        query_term_count=3,
        authorization_fingerprint="b" * 64,
        authorization_model_id="model-v1",
        tuple_version="tuples-v1",
        policy_version="policy-v1",
        authorized_scope_size=2,
        candidates=(
            CandidateAudit(
                chunk_id="chunk-1",
                document_version_id="version-1",
                lexical_rank=1,
                vector_rank=2,
                fused_rank=1,
            ),
        ),
        evidence_ids=("evidence-1",),
        document_version_ids=("version-1",),
        prompt_template_version="v1",
        model_id="local-test",
        model_version="model-v1",
        citation_validation_result="VALID",
        latency_ms_by_stage={"retrieval": 3, "total": 8},
        context_char_count=120,
        input_token_count=None,
        output_token_count=None,
        policy_warnings=("INTERNAL_CONTENT_PRESENT",),
        outcome=AuditOutcome.SUCCEEDED,
        error_class=None,
        created_at=datetime(2026, 9, 15, tzinfo=UTC),
    )


@pytest.mark.unit
@pytest.mark.security
def test_query_audit_is_content_free_and_sensitive_keys_are_dropped() -> None:
    record = _record()
    fields = query_log_fields(record)
    metadata = record.metadata_json()

    assert "query" not in fields
    assert "access_token" not in fields
    assert "internal source text" not in str(fields)
    assert "embedding vector" not in str(metadata)
    assert metadata["evidence_ids"] == ["evidence-1"]
    assert redact_mapping(
        {"token": "bearer-value", "safe_count": 1},
        allowed=frozenset({"token", "safe_count"}),
    ) == {"safe_count": 1}


@pytest.mark.unit
def test_subject_pseudonym_is_stable_and_lifecycle_events_are_typed() -> None:
    first = lifecycle_event(
        AuditEventType.ROLE_CHANGE,
        correlation_id="corr-role",
        outcome=AuditOutcome.SUCCEEDED,
        reason_code="relation_revoked",
        tenant_id="northstar",
        subject_id="user:alice",
        target_ref="resource:legal-1",
    )
    second = lifecycle_event(
        AuditEventType.ROLE_CHANGE,
        correlation_id="corr-role",
        outcome=AuditOutcome.SUCCEEDED,
        reason_code="relation_revoked",
        tenant_id="northstar",
        subject_id="user:alice",
        target_ref="resource:legal-1",
    )
    assert first.event_id == second.event_id
    assert first.pseudonymous_subject_id == second.pseudonymous_subject_id
    assert first.target_ref_hash != "resource:legal-1"


class _SecuritySink:
    def __init__(self) -> None:
        self.events: list[SecurityAuditEvent] = []

    def record_security_event(self, event: SecurityAuditEvent) -> None:
        self.events.append(event)


class _IdentityValidator:
    def validate(self, bearer_token: str, *, correlation_id: str) -> ValidatedIdentity:
        del bearer_token
        return ValidatedIdentity(
            principal=PrincipalContext(
                PrincipalId("user:alice"),
                "northstar",
                correlation_id=correlation_id,
            ),
            session_id="session-alice",
            expires_at=2_000_000_000,
        )


@pytest.mark.unit
@pytest.mark.security
def test_denied_authorization_emits_safe_event_without_resource_text() -> None:
    sink = _SecuritySink()
    bridge = AuthorizationAuditBridge(sink)
    principal = PrincipalContext(
        PrincipalId("user:alice"), "northstar", correlation_id="corr-authz"
    )
    decision = AuthorizationDecision(
        allowed=False,
        reason_code="relation_denied",
        authorization_model_id="model-v1",
        tuple_version="tuples-v1",
        decision_fingerprint="c" * 64,
        correlation_id="corr-authz",
    )

    bridge.record_authorization_decision(
        decision,
        principal=principal,
        object_id=AuthorizedObjectId("resource:legal-contract"),
        attributes={"action": "can_view", "outcome": "DENY"},
    )

    event = sink.events[0]
    assert event.event_type is AuditEventType.AUTHZ_DENIAL
    assert event.outcome is AuditOutcome.DENIED
    assert event.target_ref_hash is not None
    assert "legal-contract" not in event.target_ref_hash
    assert "resource:legal-contract" not in str(event.attributes)


@pytest.mark.unit
@pytest.mark.security
def test_authentication_emits_login_and_logout_events_without_token_material() -> None:
    sink = _SecuritySink()
    service = AuthenticationService(
        _IdentityValidator(),
        InMemorySessionRevocationStore(),
        audit_sink=sink,
    )

    service.authenticate("bearer-secret-value", correlation_id="corr-login")
    service.logout("bearer-secret-value", correlation_id="corr-logout")

    assert [event.event_type for event in sink.events] == [
        AuditEventType.LOGIN,
        AuditEventType.LOGIN,
        AuditEventType.LOGOUT,
    ]
    assert "bearer-secret-value" not in str(sink.events)


@pytest.mark.unit
@pytest.mark.security
def test_observability_domain_rejects_unbounded_or_non_utc_records() -> None:
    with pytest.raises(ValueError, match="candidate audit identity"):
        CandidateAudit("", "version-1")
    with pytest.raises(ValueError, match="query audit bounds"):
        from dataclasses import replace

        replace(_record(), query_length=0)
    with pytest.raises(ValueError, match="audit reason code"):
        SecurityAuditEvent(
            event_id=AuditEventId("audit-invalid"),
            event_type=AuditEventType.ADMIN_ACTION,
            correlation_id="corr-invalid",
            trace_id=None,
            pseudonymous_subject_id=None,
            tenant_id=None,
            outcome=AuditOutcome.FAILED,
            reason_code="",
            target_ref_hash=None,
        )


class _BrokenTelemetry:
    def span(
        self,
        name: str,
        attributes: Mapping[str, TelemetryValue] | None = None,
    ) -> AbstractContextManager[Span]:
        del name, attributes
        raise OSError("collector unavailable")

    def counter(
        self,
        name: str,
        value: int = 1,
        attributes: Mapping[str, TelemetryValue] | None = None,
    ) -> None:
        del name, value, attributes
        raise OSError("collector unavailable")


@pytest.mark.unit
@pytest.mark.security
def test_telemetry_outage_is_best_effort_and_does_not_swallow_work_errors() -> None:
    telemetry = BestEffortTelemetry(_BrokenTelemetry())
    with telemetry.span("knowledge.query"):
        pass
    telemetry.counter("knowledge.query.completed")
    with (
        pytest.raises(RuntimeError, match="protected failure"),
        telemetry.span("knowledge.query"),
    ):
        raise RuntimeError("protected failure")
