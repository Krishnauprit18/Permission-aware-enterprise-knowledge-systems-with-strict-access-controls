"""P16 product API contract and browser-boundary regressions."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from time import time

import httpx
import pytest

from knowledge_system.application.authentication import (
    AuthenticationService,
    InMemorySessionRevocationStore,
)
from knowledge_system.application.ports.authentication import ValidatedIdentity
from knowledge_system.domain.contracts import EvidenceId, PrincipalContext, PrincipalId
from knowledge_system.domain.generation import (
    CitationValidationStatus,
    GenerationOutcome,
    GenerationTrace,
    GroundedAnswer,
    GroundedClaim,
    ValidatedCitation,
)
from knowledge_system.domain.persistence import Classification
from knowledge_system.domain.policy import (
    AnswerMode,
    PolicyStatus,
    PolicyWarning,
    PolicyWarningCode,
    PolicyWarningSeverity,
)
from knowledge_system.entrypoints.api.main import app


@dataclass(slots=True)
class StaticValidator:
    identity: ValidatedIdentity

    def validate(self, bearer_token: str, *, correlation_id: str) -> ValidatedIdentity:
        del bearer_token, correlation_id
        return self.identity


@dataclass(slots=True)
class FakeQueryService:
    answer_value: GroundedAnswer
    calls: list[tuple[PrincipalContext, str, AnswerMode]]

    def answer(
        self, principal: PrincipalContext, question: str, mode: AnswerMode
    ) -> GroundedAnswer:
        self.calls.append((principal, question, mode))
        return self.answer_value


def _answer() -> GroundedAnswer:
    timestamp = datetime(2026, 9, 8, tzinfo=UTC)
    evidence_id = EvidenceId("evidence_api_fixture")
    citation = ValidatedCitation(
        evidence_id=evidence_id,
        quote="Approved date: September 24.",
        source_type="document",
        source_locator=("Release board", "section:decision"),
        source_url="https://docs.northstar.invalid/acme/release",
        updated_at=timestamp,
        classification=Classification.INTERNAL,
    )
    trace = GenerationTrace(
        correlation_id="api-correlation",
        authorization_fingerprint="fingerprint-api",
        prompt_purpose="grounded-answer",
        prompt_version="v1",
        prompt_hash="prompt-hash",
        model_id="local-test",
        model_version="test-v1",
        evidence_ids=(evidence_id,),
        context_char_count=28,
        attempts=1,
        citation_validation=CitationValidationStatus.VALID,
        outcome=GenerationOutcome.ANSWERED,
        latency_ms=2,
        created_at=timestamp,
    )
    return GroundedAnswer(
        outcome=GenerationOutcome.ANSWERED,
        message="Answer grounded in accessible evidence.",
        claims=(
            GroundedClaim("The approved rollout date is September 24.", (citation,)),
        ),
        conflicts=(),
        qualifications=(),
        trace=trace,
        answer_mode=AnswerMode.INTERNAL,
        policy_status=PolicyStatus.ALLOW_WITH_WARNINGS,
        policy_warnings=(
            PolicyWarning(
                PolicyWarningCode.INTERNAL_CONTENT_PRESENT,
                PolicyWarningSeverity.WARNING,
                "Internal content warning.",
            ),
        ),
    )


@pytest.fixture
def configured_api() -> tuple[FakeQueryService, None]:
    identity = ValidatedIdentity(
        principal=PrincipalContext(
            subject_id=PrincipalId("user:alice"),
            tenant_id="northstar",
            groups=("sales-customer-success",),
        ),
        session_id="api-session",
        expires_at=int(time()) + 300,
    )
    service = FakeQueryService(_answer(), [])
    app.state.authentication_service = AuthenticationService(
        StaticValidator(identity), InMemorySessionRevocationStore()
    )
    app.state.query_service = service
    return service, None


def request(method: str, path: str, *, json: object | None = None) -> httpx.Response:
    async def send() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.request(
                method,
                path,
                headers={"Authorization": "Bearer synthetic-token"},
                json=json,
            )

    return asyncio.run(send())


@pytest.mark.integration
@pytest.mark.security
def test_query_projects_only_backend_citations_and_policy_metadata(
    configured_api: tuple[FakeQueryService, None],
) -> None:
    service, _ = configured_api
    response = request(
        "POST",
        "/api/v1/knowledge/query",
        json={"question": "What is the date?", "mode": "INTERNAL"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["claims"][0]["citations"][0]["evidence_id"] == "evidence_api_fixture"
    assert body["citations"][0]["excerpt"] == "Approved date: September 24."
    assert body["warnings"][0]["code"] == "INTERNAL_CONTENT_PRESENT"
    assert service.calls[0][0].correlation_id == response.headers["X-Correlation-ID"]
    assert (
        response.headers["content-security-policy"]
        == "default-src 'none'; frame-ancestors 'none'"
    )


@pytest.mark.integration
@pytest.mark.security
def test_customer_safe_mode_reaches_service_as_distinct_request(
    configured_api: tuple[FakeQueryService, None],
) -> None:
    service, _ = configured_api
    response = request(
        "POST",
        "/api/v1/knowledge/query",
        json={"question": "Prepare an update", "mode": "CUSTOMER_SAFE"},
    )
    assert response.status_code == 200
    assert service.calls[0][2] is AnswerMode.CUSTOMER_SAFE


@pytest.mark.integration
@pytest.mark.security
def test_unconfigured_query_service_fails_closed_without_stack_trace(
    configured_api: tuple[FakeQueryService, None],
) -> None:
    del configured_api
    app.state.query_service = None
    response = request("POST", "/api/v1/knowledge/query", json={"question": "Anything"})
    assert response.status_code == 503
    assert response.json()["code"] == "QUERY_SERVICE_UNAVAILABLE"
    assert "Traceback" not in response.text


@pytest.mark.integration
@pytest.mark.security
def test_invalid_query_is_generic_and_bounded(
    configured_api: tuple[FakeQueryService, None],
) -> None:
    del configured_api
    response = request(
        "POST",
        "/api/v1/knowledge/query",
        json={"question": "x" * 2_001, "unexpected": "filter widening"},
    )
    assert response.status_code == 422
    assert response.json() == {
        "code": "INVALID_REQUEST",
        "message": "The request is invalid.",
        "request_id": response.headers["X-Correlation-ID"],
    }


@pytest.mark.integration
def test_openapi_exposes_versioned_product_contract(
    configured_api: tuple[FakeQueryService, None],
) -> None:
    del configured_api
    response = request("GET", "/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/api/v1/knowledge/query" in schema["paths"]
    assert "QueryRequest" in schema["components"]["schemas"]
    assert "ErrorResponse" in schema["components"]["schemas"]
