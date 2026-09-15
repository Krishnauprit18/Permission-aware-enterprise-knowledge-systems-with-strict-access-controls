"""Protected query orchestration for the product API composition root."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import monotonic
from typing import Protocol

from knowledge_system.application.confidentiality import PolicyAwareGenerationService
from knowledge_system.application.evidence import EvidenceResolutionService
from knowledge_system.application.ports.observability import (
    AuditLogger,
    BestEffortTelemetry,
    NoopTelemetry,
    QueryAuditSink,
    TelemetryPort,
)
from knowledge_system.application.retrieval import PermissionFirstRetrievalService
from knowledge_system.domain.contracts import PrincipalContext
from knowledge_system.domain.evidence import EvidenceResolution
from knowledge_system.domain.generation import GenerationOutcome, GroundedAnswer
from knowledge_system.domain.observability import (
    AuditOutcome,
    CandidateAudit,
    QueryAuditRecord,
    normalized_query_metadata,
    pseudonymous_subject_id,
)
from knowledge_system.domain.policy import AnswerMode
from knowledge_system.domain.retrieval import RetrievalRequest, RetrievalResult


class RetrievalUseCase(Protocol):
    def retrieve(
        self, principal: PrincipalContext, request: RetrievalRequest
    ) -> RetrievalResult: ...


class EvidenceUseCase(Protocol):
    def resolve(
        self, principal: PrincipalContext, question: str, retrieval: RetrievalResult
    ) -> EvidenceResolution: ...


class GenerationUseCase(Protocol):
    def answer(
        self,
        principal: PrincipalContext,
        question: str,
        resolution: EvidenceResolution,
        *,
        mode: AnswerMode,
    ) -> GroundedAnswer: ...


@dataclass(slots=True)
class KnowledgeQueryApplication:
    """Keep the protected stage order in one injectable application service."""

    retrieval: RetrievalUseCase
    evidence: EvidenceUseCase
    generation: GenerationUseCase
    telemetry: TelemetryPort = field(default_factory=NoopTelemetry)
    audit_sink: QueryAuditSink | None = None
    audit_logger: AuditLogger | None = None

    def __post_init__(self) -> None:
        self.telemetry = BestEffortTelemetry(self.telemetry)

    def answer(
        self, principal: PrincipalContext, question: str, mode: AnswerMode
    ) -> GroundedAnswer:
        started = monotonic()
        stage_latency: dict[str, int] = {}
        retrieval: RetrievalResult | None = None
        resolution: EvidenceResolution | None = None
        answer: GroundedAnswer | None = None
        failure: BaseException | None = None
        with self.telemetry.span(
            "knowledge.query",
            {
                "tenant.id": principal.tenant_id,
                "request.correlation_id": principal.correlation_id,
                "answer.mode": mode.value,
            },
        ):
            try:
                stage_started = monotonic()
                with self.telemetry.span("knowledge.query.retrieval"):
                    retrieval = self.retrieval.retrieve(
                        principal, RetrievalRequest(question=question)
                    )
                stage_latency["retrieval"] = _elapsed_ms(stage_started)

                stage_started = monotonic()
                with self.telemetry.span("knowledge.query.evidence"):
                    if retrieval is None:
                        raise RuntimeError("retrieval stage returned no result")
                    resolution = self.evidence.resolve(principal, question, retrieval)
                stage_latency["evidence"] = _elapsed_ms(stage_started)

                stage_started = monotonic()
                with self.telemetry.span("knowledge.query.generation"):
                    if resolution is None:
                        raise RuntimeError("evidence stage returned no result")
                    answer = self.generation.answer(
                        principal, question, resolution, mode=mode
                    )
                stage_latency["generation"] = _elapsed_ms(stage_started)
                return answer
            except BaseException as error:
                failure = error
                raise
            finally:
                stage_latency["total"] = _elapsed_ms(started)
                record = _query_audit_record(
                    principal=principal,
                    question=question,
                    retrieval=retrieval,
                    resolution=resolution,
                    answer=answer,
                    failure=failure,
                    latency_ms_by_stage=stage_latency,
                )
                self._record_audit(record)

    def _record_audit(self, record: QueryAuditRecord) -> None:
        """Keep telemetry outage from changing authorization or answer behavior."""

        if self.audit_sink is not None:
            try:
                self.audit_sink.record_query(record)
            except (OSError, RuntimeError, ValueError):
                self.telemetry.counter("knowledge.audit.write_failures")
        if self.audit_logger is not None:
            try:
                self.audit_logger.query(record)
            except (OSError, RuntimeError, ValueError):
                self.telemetry.counter("knowledge.audit.log_failures")


def build_query_application(
    retrieval: PermissionFirstRetrievalService,
    evidence: EvidenceResolutionService,
    generation: PolicyAwareGenerationService,
) -> KnowledgeQueryApplication:
    """Build the production-shaped pipeline without choosing infrastructure here."""

    return KnowledgeQueryApplication(retrieval, evidence, generation)


def _elapsed_ms(started: float) -> int:
    return max(0, round((monotonic() - started) * 1_000))


def _query_audit_record(
    *,
    principal: PrincipalContext,
    question: str,
    retrieval: RetrievalResult | None,
    resolution: EvidenceResolution | None,
    answer: GroundedAnswer | None,
    failure: BaseException | None,
    latency_ms_by_stage: dict[str, int],
) -> QueryAuditRecord:
    query_hash, query_length, query_term_count = normalized_query_metadata(question)
    retrieval_trace = retrieval.trace if retrieval is not None else None
    authorization_fingerprint = (
        retrieval_trace.authorization_fingerprint
        if retrieval_trace is not None
        else (
            answer.trace.authorization_fingerprint
            if answer is not None
            else "unavailable"
        )
    )
    candidates = _candidate_audit(retrieval, resolution)
    evidence_ids = (
        tuple(str(value) for value in answer.trace.evidence_ids)
        if answer is not None
        else ()
    )
    document_version_ids = tuple(
        sorted(
            {
                candidate.document_version_id
                for candidate in (retrieval.candidates if retrieval else ())
                if candidate.document_version_id.strip()
            }
            | {
                packet.document_version_id
                for packet in (resolution.packets if resolution else ())
            }
        )
    )
    outcome = (
        _audit_outcome(answer.outcome)
        if answer is not None
        else AuditOutcome.FAILED
        if failure is not None
        else AuditOutcome.REFUSED
    )
    return QueryAuditRecord(
        trace_id=principal.correlation_id or "query-unavailable",
        correlation_id=principal.correlation_id or "query-unavailable",
        pseudonymous_subject_id=pseudonymous_subject_id(str(principal.subject_id)),
        tenant_id=principal.tenant_id,
        query_hash=query_hash,
        query_length=query_length,
        query_term_count=query_term_count,
        authorization_fingerprint=authorization_fingerprint,
        authorization_model_id=(
            retrieval_trace.authorization_model_id
            if retrieval_trace is not None
            else "unavailable"
        ),
        tuple_version=(
            retrieval_trace.tuple_version
            if retrieval_trace is not None
            else "unavailable"
        ),
        policy_version=(
            retrieval_trace.policy_version
            if retrieval_trace is not None
            else "unavailable"
        ),
        authorized_scope_size=(
            retrieval_trace.authorized_scope_size if retrieval_trace is not None else 0
        ),
        candidates=candidates,
        evidence_ids=evidence_ids,
        document_version_ids=document_version_ids,
        prompt_template_version=(
            answer.trace.prompt_version if answer is not None else "unavailable"
        ),
        model_id=answer.trace.model_id if answer is not None else "unavailable",
        model_version=(
            answer.trace.model_version if answer is not None else "unavailable"
        ),
        citation_validation_result=(
            answer.trace.citation_validation.value
            if answer is not None
            else "NOT_ATTEMPTED"
        ),
        latency_ms_by_stage=dict(latency_ms_by_stage),
        context_char_count=answer.trace.context_char_count if answer is not None else 0,
        input_token_count=None,
        output_token_count=None,
        policy_warnings=(
            tuple(warning.code.value for warning in answer.policy_warnings)
            if answer is not None
            else ()
        ),
        outcome=outcome,
        error_class=(
            type(failure).__name__.upper()[:64] if failure is not None else None
        ),
        created_at=(
            answer.trace.created_at if answer is not None else datetime.now(UTC)
        ),
    )


def _candidate_audit(
    retrieval: RetrievalResult | None, resolution: EvidenceResolution | None
) -> tuple[CandidateAudit, ...]:
    if retrieval is None:
        return ()
    diagnostics = {
        item.chunk_id: item for item in retrieval.trace.component_diagnostics
    }
    audited: list[CandidateAudit] = []
    for index, candidate in enumerate(retrieval.candidates, start=1):
        diagnostic = diagnostics.get(candidate.chunk_id)
        audited.append(
            CandidateAudit(
                chunk_id=candidate.chunk_id,
                document_version_id=candidate.document_version_id,
                fused_rank=index,
                lexical_rank=diagnostic.lexical_rank if diagnostic else None,
                vector_rank=diagnostic.vector_rank if diagnostic else None,
                lexical_score=diagnostic.lexical_score if diagnostic else None,
                vector_score=diagnostic.vector_score if diagnostic else None,
                rerank_rank=_rerank_rank(candidate.chunk_id, resolution),
            )
        )
    return tuple(audited)


def _rerank_rank(chunk_id: str, resolution: EvidenceResolution | None) -> int | None:
    if resolution is None:
        return None
    for packet in resolution.packets:
        if packet.chunk_id == chunk_id:
            return packet.diagnostics.rerank_rank
    return None


def _audit_outcome(outcome: GenerationOutcome) -> AuditOutcome:
    if outcome is GenerationOutcome.ANSWERED:
        return AuditOutcome.SUCCEEDED
    if outcome is GenerationOutcome.REFUSED:
        return AuditOutcome.REFUSED
    return AuditOutcome.FAILED
