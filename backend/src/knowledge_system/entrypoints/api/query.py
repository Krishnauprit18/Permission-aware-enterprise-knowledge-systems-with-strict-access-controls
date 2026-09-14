"""Versioned product query contract and safe response projection."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from knowledge_system.application.ports.authentication import ValidatedIdentity
from knowledge_system.application.ports.query import QueryAnswerService
from knowledge_system.domain.generation import GroundedAnswer
from knowledge_system.domain.policy import AnswerMode
from knowledge_system.entrypoints.api.auth import current_identity, get_correlation_id

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


class QueryRequest(BaseModel):
    """Bounded user input; no client-side ACL or search DSL is accepted."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2_000)
    mode: AnswerMode = AnswerMode.INTERNAL


class CitationResponse(BaseModel):
    """Backend-owned citation metadata and a permitted excerpt."""

    evidence_id: str
    title: str
    source_type: str
    source_locator: tuple[str, ...]
    source_url: str | None
    updated_at: datetime
    classification: str
    excerpt: str


class ClaimResponse(BaseModel):
    text: str
    citations: tuple[CitationResponse, ...]


class ConflictResponse(BaseModel):
    evidence_ids: tuple[str, ...]
    most_authoritative_evidence_id: str


class QualificationResponse(BaseModel):
    evidence_id: str
    decision_status: str
    freshness: str


class WarningResponse(BaseModel):
    code: str
    severity: str
    message: str


class QueryTraceResponse(BaseModel):
    request_id: str
    authorization_fingerprint: str
    evidence_ids: tuple[str, ...]
    prompt_version: str
    model_id: str
    model_version: str


class QueryResponse(BaseModel):
    """Stable answer envelope without hidden model reasoning or raw trace data."""

    outcome: str
    message: str
    answer_mode: AnswerMode
    policy_status: str
    claims: tuple[ClaimResponse, ...]
    citations: tuple[CitationResponse, ...]
    conflicts: tuple[ConflictResponse, ...]
    qualifications: tuple[QualificationResponse, ...]
    warnings: tuple[WarningResponse, ...]
    trace: QueryTraceResponse


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str


@router.post(
    "/query",
    response_model=QueryResponse,
    responses={503: {"model": ErrorResponse}},
)
async def query_knowledge(
    payload: QueryRequest,
    request: Request,
    identity: ValidatedIdentity = Depends(current_identity),  # noqa: B008
) -> QueryResponse:
    """Run a server-owned answer pipeline for the authenticated principal."""

    correlation_id = get_correlation_id(request)
    service = getattr(request.app.state, "query_service", None)
    if service is None:
        return cast(QueryResponse, service_error_response(correlation_id))
    query_service = cast(QueryAnswerService, service)
    principal = replace(identity.principal, correlation_id=correlation_id)
    try:
        answer = query_service.answer(principal, payload.question, payload.mode)
    except (OSError, RuntimeError, ValueError) as exc:
        del exc
        return cast(QueryResponse, service_error_response(correlation_id))
    return _project_answer(answer, correlation_id)


def _project_answer(answer: GroundedAnswer, request_id: str) -> QueryResponse:
    citations_by_id: dict[str, CitationResponse] = {}
    claims: list[ClaimResponse] = []
    for claim in answer.claims:
        claim_citations: list[CitationResponse] = []
        for citation in claim.citations:
            evidence_id = str(citation.evidence_id)
            projected = citations_by_id.get(evidence_id)
            if projected is None:
                title = (
                    citation.source_locator[0]
                    if citation.source_locator
                    else citation.source_type
                )
                projected = CitationResponse(
                    evidence_id=evidence_id,
                    title=title,
                    source_type=citation.source_type,
                    source_locator=citation.source_locator,
                    source_url=citation.source_url,
                    updated_at=citation.updated_at,
                    classification=citation.classification.value,
                    excerpt=citation.quote,
                )
                citations_by_id[evidence_id] = projected
            claim_citations.append(projected)
        claims.append(ClaimResponse(text=claim.text, citations=tuple(claim_citations)))

    return QueryResponse(
        outcome=answer.outcome.value,
        message=answer.message,
        answer_mode=answer.answer_mode,
        policy_status=answer.policy_status.value,
        claims=tuple(claims),
        citations=tuple(citations_by_id.values()),
        conflicts=tuple(
            ConflictResponse(
                evidence_ids=tuple(str(value) for value in conflict.evidence_ids),
                most_authoritative_evidence_id=str(
                    conflict.most_authoritative_evidence_id
                ),
            )
            for conflict in answer.conflicts
        ),
        qualifications=tuple(
            QualificationResponse(
                evidence_id=str(qualification.evidence_id),
                decision_status=qualification.decision_status.value,
                freshness=qualification.freshness.value,
            )
            for qualification in answer.qualifications
        ),
        warnings=tuple(
            WarningResponse(
                code=warning.code.value,
                severity=warning.severity.value,
                message=warning.message,
            )
            for warning in answer.policy_warnings
        ),
        trace=QueryTraceResponse(
            request_id=request_id,
            authorization_fingerprint=answer.trace.authorization_fingerprint,
            evidence_ids=tuple(str(value) for value in answer.trace.evidence_ids),
            prompt_version=answer.trace.prompt_version,
            model_id=answer.trace.model_id,
            model_version=answer.trace.model_version,
        ),
    )


def service_error_response(request_id: str) -> JSONResponse:
    """Return the same generic shape for composition-root failures."""

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=ErrorResponse(
            code="QUERY_SERVICE_UNAVAILABLE",
            message="The answer service is temporarily unavailable.",
            request_id=request_id,
        ).model_dump(),
    )
