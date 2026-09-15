"""Protected stage-order regression tests for the P16 application port."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass

import pytest

from knowledge_system.application.query import KnowledgeQueryApplication
from knowledge_system.domain.contracts import PrincipalContext, PrincipalId
from knowledge_system.domain.evidence import EvidenceResolution
from knowledge_system.domain.generation import GroundedAnswer
from knowledge_system.domain.observability import QueryAuditRecord
from knowledge_system.domain.policy import AnswerMode
from knowledge_system.domain.retrieval import (
    RetrievalRequest,
    RetrievalResult,
    RetrievalTrace,
)


@dataclass(slots=True)
class FakeRetrieval:
    events: list[str]

    def retrieve(
        self, principal: PrincipalContext, request: RetrievalRequest
    ) -> RetrievalResult:
        del principal
        self.events.append(f"retrieve:{request.question}")
        return RetrievalResult((), _trace())


@dataclass(slots=True)
class FakeEvidence:
    events: list[str]

    def resolve(
        self, principal: PrincipalContext, question: str, retrieval: RetrievalResult
    ) -> EvidenceResolution:
        del principal, retrieval
        self.events.append(f"evidence:{question}")
        return _resolution()


@dataclass(slots=True)
class FakeGeneration:
    events: list[str]
    answer_value: GroundedAnswer

    def answer(
        self,
        principal: PrincipalContext,
        question: str,
        resolution: EvidenceResolution,
        *,
        mode: AnswerMode,
    ) -> GroundedAnswer:
        del principal, resolution
        self.events.append(f"generation:{question}:{mode.value}")
        return self.answer_value


@dataclass(slots=True)
class CapturingAudit:
    records: list[QueryAuditRecord]

    def record_query(self, record: QueryAuditRecord) -> None:
        self.records.append(record)


@dataclass(slots=True)
class FailingAudit:
    def record_query(self, record: QueryAuditRecord) -> None:
        del record
        raise OSError("audit store unavailable")


class FakeSpan:
    def set_attribute(self, key: str, value: str | float | bool) -> None:
        del key, value

    def record_exception(self, error: BaseException) -> None:
        del error


@dataclass(slots=True)
class CapturingTelemetry:
    spans: list[str]
    counters: list[str]

    @contextmanager
    def span(
        self,
        name: str,
        attributes: Mapping[str, str | int | float | bool] | None = None,
    ) -> Iterator[FakeSpan]:
        del attributes
        self.spans.append(name)
        yield FakeSpan()

    def counter(
        self,
        name: str,
        value: int = 1,
        attributes: Mapping[str, str | int | float | bool] | None = None,
    ) -> None:
        del value, attributes
        self.counters.append(name)


def _principal() -> PrincipalContext:
    return PrincipalContext(
        PrincipalId("user:test"), "northstar", correlation_id="query-test"
    )


def _trace() -> RetrievalTrace:
    return RetrievalTrace("query-test", "fingerprint", 0, 0, 0, 0, 0, ())


def _resolution() -> EvidenceResolution:
    from knowledge_system.domain.evidence import EvidenceResolutionTrace

    return EvidenceResolution(
        (),
        (),
        (),
        None,
        None,
        EvidenceResolutionTrace(
            "query-test", "fingerprint", "reranker", 0, 0, 0, 0, 0, False
        ),
    )


def _answer() -> GroundedAnswer:
    from datetime import UTC, datetime

    from knowledge_system.domain.generation import (
        CitationValidationStatus,
        GenerationOutcome,
        GenerationTrace,
    )
    from knowledge_system.domain.policy import PolicyStatus

    timestamp = datetime(2026, 9, 1, tzinfo=UTC)
    return GroundedAnswer(
        GenerationOutcome.REFUSED,
        "Not enough evidence.",
        (),
        (),
        (),
        GenerationTrace(
            "query-test",
            "fingerprint",
            "prompt",
            "v1",
            "hash",
            "local",
            "v1",
            (),
            0,
            0,
            CitationValidationStatus.NOT_ATTEMPTED,
            GenerationOutcome.REFUSED,
            0,
            timestamp,
        ),
        policy_status=PolicyStatus.REFUSED,
    )


@pytest.mark.unit
def test_application_preserves_authorization_before_evidence_and_generation() -> None:
    events: list[str] = []
    app = KnowledgeQueryApplication(
        FakeRetrieval(events), FakeEvidence(events), FakeGeneration(events, _answer())
    )
    result = app.answer(_principal(), "What is approved?", AnswerMode.CUSTOMER_SAFE)
    assert result.outcome.value == "REFUSED"
    assert events == [
        "retrieve:What is approved?",
        "evidence:What is approved?",
        "generation:What is approved?:CUSTOMER_SAFE",
    ]


@pytest.mark.unit
@pytest.mark.security
def test_application_records_content_free_audit_and_nested_stage_spans() -> None:
    events: list[str] = []
    audit = CapturingAudit([])
    telemetry = CapturingTelemetry([], [])
    app = KnowledgeQueryApplication(
        FakeRetrieval(events),
        FakeEvidence(events),
        FakeGeneration(events, _answer()),
        telemetry=telemetry,
        audit_sink=audit,
    )

    app.answer(_principal(), "What is approved?", AnswerMode.INTERNAL)

    record = audit.records[0]
    assert record.query_hash != "What is approved?"
    assert record.pseudonymous_subject_id != "user:test"
    assert record.evidence_ids == ()
    assert telemetry.spans == [
        "knowledge.query",
        "knowledge.query.retrieval",
        "knowledge.query.evidence",
        "knowledge.query.generation",
    ]


@pytest.mark.unit
@pytest.mark.security
def test_audit_outage_does_not_change_answer_or_authorization_order() -> None:
    events: list[str] = []
    telemetry = CapturingTelemetry([], [])
    app = KnowledgeQueryApplication(
        FakeRetrieval(events),
        FakeEvidence(events),
        FakeGeneration(events, _answer()),
        telemetry=telemetry,
        audit_sink=FailingAudit(),
    )

    result = app.answer(_principal(), "What is approved?", AnswerMode.INTERNAL)

    assert result.outcome.value == "REFUSED"
    assert events == [
        "retrieve:What is approved?",
        "evidence:What is approved?",
        "generation:What is approved?:INTERNAL",
    ]
    assert telemetry.counters == ["knowledge.audit.write_failures"]
