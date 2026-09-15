"""Deterministic retrieval, generation, and security metrics for P18."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from math import log2

from knowledge_system.evaluation.contracts import (
    GenerationObservation,
    GoldenCase,
    RetrievalObservation,
)


@dataclass(frozen=True, slots=True)
class RetrievalEvaluation:
    """Retrieval-only aggregate; it never reads answer or citation fields."""

    case_count: int
    recall_at_k: Mapping[str, float]
    precision_at_k: Mapping[str, float]
    mrr: float
    ndcg: float
    unauthorized_context_rate: float
    cross_tenant_leakage: int
    security_passed: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "case_count": self.case_count,
            "recall_at_k": dict(self.recall_at_k),
            "precision_at_k": dict(self.precision_at_k),
            "mrr": self.mrr,
            "ndcg": self.ndcg,
            "unauthorized_context_rate": self.unauthorized_context_rate,
            "cross_tenant_leakage": self.cross_tenant_leakage,
            "security_passed": self.security_passed,
        }


@dataclass(frozen=True, slots=True)
class GenerationEvaluation:
    """Generation-only aggregate over structured answer metadata."""

    case_count: int
    grounded_correctness: float
    citation_precision: float
    citation_recall: float
    citation_support: float
    conflict_handling: float
    temporal_correctness: float
    refusal_correctness: float
    warning_correctness: float
    invalid_citation_acceptance: int
    security_passed: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "case_count": self.case_count,
            "grounded_correctness": self.grounded_correctness,
            "citation_precision": self.citation_precision,
            "citation_recall": self.citation_recall,
            "citation_support": self.citation_support,
            "conflict_handling": self.conflict_handling,
            "temporal_correctness": self.temporal_correctness,
            "refusal_correctness": self.refusal_correctness,
            "warning_correctness": self.warning_correctness,
            "invalid_citation_acceptance": self.invalid_citation_acceptance,
            "security_passed": self.security_passed,
        }


def evaluate_retrieval(
    cases: Sequence[GoldenCase],
    observations: Sequence[RetrievalObservation],
    *,
    ks: Sequence[int] = (1, 3, 5, 10),
) -> RetrievalEvaluation:
    """Calculate ranking metrics and fail-closed security metrics."""

    by_id = _observations_by_case(observations)
    recall: dict[str, float] = {}
    precision: dict[str, float] = {}
    for k in ks:
        recalls: list[float] = []
        precisions: list[float] = []
        for case in cases:
            observation = by_id.get(case.case_id)
            ranked = observation.ranked_ids[:k] if observation else ()
            relevant = set(case.expected_relevant_ids)
            hits = len(set(ranked) & relevant)
            if relevant:
                recalls.append(hits / len(relevant))
                precisions.append(hits / k)
        recall[str(k)] = _mean(recalls)
        precision[str(k)] = _mean(precisions)

    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    unauthorized = 0
    context_total = 0
    cross_tenant = 0
    for case in cases:
        observation = by_id.get(case.case_id)
        if observation is None:
            continue
        relevant = set(case.expected_relevant_ids)
        reciprocal_ranks.append(_reciprocal_rank(observation.ranked_ids, relevant))
        ndcgs.append(
            _ndcg(observation.ranked_ids, relevant, observation.relevance_grades)
        )
        allowed = set(observation.allowed_ids)
        protected_ids = set(observation.ranked_ids) | set(observation.context_ids)
        for item_id in protected_ids:
            if observation.tenant_by_id.get(item_id) != case.tenant_id:
                cross_tenant += 1
        for item_id in observation.context_ids:
            context_total += 1
            if item_id not in allowed or item_id in case.forbidden_ids:
                unauthorized += 1
    ucr = unauthorized / context_total if context_total else 0.0
    return RetrievalEvaluation(
        case_count=len(cases),
        recall_at_k=recall,
        precision_at_k=precision,
        mrr=_mean(reciprocal_ranks),
        ndcg=_mean(ndcgs),
        unauthorized_context_rate=ucr,
        cross_tenant_leakage=cross_tenant,
        security_passed=unauthorized == 0 and cross_tenant == 0,
    )


def evaluate_generation(
    cases: Sequence[GoldenCase],
    observations: Sequence[GenerationObservation],
) -> GenerationEvaluation:
    """Evaluate structured answers without re-evaluating retrieval ranking."""

    by_id = _observations_by_case(observations)
    grounded: list[float] = []
    citation_precision: list[float] = []
    citation_recall: list[float] = []
    citation_support: list[float] = []
    conflicts: list[float] = []
    temporal: list[float] = []
    refusals: list[float] = []
    warnings: list[float] = []
    invalid_accepted = 0
    for case in cases:
        observation = by_id.get(case.case_id)
        if observation is None:
            continue
        expected_claims = set(case.expected_claim_keys)
        observed_claims = set(observation.claim_keys)
        grounded.append(
            float(case.expected_refusal == observation.refused)
            if case.expected_refusal
            else _set_recall(expected_claims, observed_claims)
        )
        expected_citations = set(case.expected_citation_ids)
        observed_citations = set(observation.citation_ids)
        citation_precision.append(
            _set_precision(expected_citations, observed_citations)
        )
        citation_recall.append(_set_recall(expected_citations, observed_citations))
        citation_support.append(
            _set_recall(observed_citations, set(observation.supported_citation_ids))
        )
        conflicts.append(float(observation.conflict_handled == case.expected_conflict))
        temporal.append(float(observation.temporal_correct))
        refusals.append(float(observation.refused == case.expected_refusal))
        warnings.append(
            _set_precision(
                set(case.expected_warning_codes), set(observation.warning_codes)
            )
            if case.expected_warning_codes
            else float(not observation.warning_codes)
        )
        invalid_accepted += observation.invalid_citation_accepted
        invalid_accepted += len(
            (set(observation.citation_ids) - set(observation.provided_evidence_ids))
            | (set(observation.citation_ids) & set(case.forbidden_ids))
        )
    return GenerationEvaluation(
        case_count=len(cases),
        grounded_correctness=_mean(grounded),
        citation_precision=_mean(citation_precision),
        citation_recall=_mean(citation_recall),
        citation_support=_mean(citation_support),
        conflict_handling=_mean(conflicts),
        temporal_correctness=_mean(temporal),
        refusal_correctness=_mean(refusals),
        warning_correctness=_mean(warnings),
        invalid_citation_acceptance=invalid_accepted,
        security_passed=invalid_accepted == 0,
    )


def _observations_by_case[Observation: RetrievalObservation | GenerationObservation](
    values: Iterable[Observation],
) -> dict[str, Observation]:
    result: dict[str, Observation] = {}
    for value in values:
        case_id = value.case_id
        if case_id in result:
            raise ValueError(f"duplicate observation for {case_id}")
        result[case_id] = value
    return result


def _reciprocal_rank(ranked: Sequence[str], relevant: set[str]) -> float:
    for index, item_id in enumerate(ranked, start=1):
        if item_id in relevant:
            return 1.0 / index
    return 0.0


def _ndcg(
    ranked: Sequence[str], relevant: set[str], grades: Mapping[str, int]
) -> float:
    if not relevant:
        return 1.0
    dcg = sum(
        (2 ** grades.get(item_id, 1) - 1) / log2(index + 1)
        for index, item_id in enumerate(ranked, start=1)
        if item_id in relevant
    )
    ideal = sorted((grades.get(item_id, 1) for item_id in relevant), reverse=True)
    idcg = sum((2**grade - 1) / log2(index + 1) for index, grade in enumerate(ideal, 1))
    return dcg / idcg if idcg else 0.0


def _set_precision(expected: set[str], observed: set[str]) -> float:
    return len(expected & observed) / len(observed) if observed else float(not expected)


def _set_recall(expected: set[str], observed: set[str]) -> float:
    return len(expected & observed) / len(expected) if expected else float(not observed)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0
