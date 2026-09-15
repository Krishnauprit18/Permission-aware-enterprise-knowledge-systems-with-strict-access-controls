"""Deterministic, local-only evaluation contracts and metric runners."""

from knowledge_system.evaluation.contracts import GoldenCase
from knowledge_system.evaluation.metrics import (
    GenerationEvaluation,
    RetrievalEvaluation,
    evaluate_generation,
    evaluate_retrieval,
)

__all__ = [
    "GenerationEvaluation",
    "GoldenCase",
    "RetrievalEvaluation",
    "evaluate_generation",
    "evaluate_retrieval",
]
