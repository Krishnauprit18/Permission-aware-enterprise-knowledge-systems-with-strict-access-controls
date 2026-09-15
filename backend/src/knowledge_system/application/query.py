"""Protected query orchestration for the product API composition root."""

from dataclasses import dataclass
from typing import Protocol

from knowledge_system.application.confidentiality import PolicyAwareGenerationService
from knowledge_system.application.evidence import EvidenceResolutionService
from knowledge_system.application.retrieval import PermissionFirstRetrievalService
from knowledge_system.domain.contracts import PrincipalContext
from knowledge_system.domain.evidence import EvidenceResolution
from knowledge_system.domain.generation import GroundedAnswer
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

    def answer(
        self, principal: PrincipalContext, question: str, mode: AnswerMode
    ) -> GroundedAnswer:
        retrieval = self.retrieval.retrieve(
            principal, RetrievalRequest(question=question)
        )
        resolution = self.evidence.resolve(principal, question, retrieval)
        return self.generation.answer(principal, question, resolution, mode=mode)


def build_query_application(
    retrieval: PermissionFirstRetrievalService,
    evidence: EvidenceResolutionService,
    generation: PolicyAwareGenerationService,
) -> KnowledgeQueryApplication:
    """Build the production-shaped pipeline without choosing infrastructure here."""

    return KnowledgeQueryApplication(retrieval, evidence, generation)
