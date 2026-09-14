"""Application boundary for authenticated product queries."""

from typing import Protocol

from knowledge_system.domain.contracts import PrincipalContext
from knowledge_system.domain.generation import GroundedAnswer
from knowledge_system.domain.policy import AnswerMode


class QueryAnswerService(Protocol):
    """Answer a bounded question after the complete protected pipeline."""

    def answer(
        self,
        principal: PrincipalContext,
        question: str,
        mode: AnswerMode,
    ) -> GroundedAnswer: ...
