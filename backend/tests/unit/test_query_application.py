"""Protected stage-order regression tests for the P16 application port."""

from dataclasses import dataclass

import pytest

from knowledge_system.application.query import KnowledgeQueryApplication
from knowledge_system.domain.contracts import PrincipalContext, PrincipalId
from knowledge_system.domain.evidence import EvidenceResolution
from knowledge_system.domain.generation import GroundedAnswer
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
