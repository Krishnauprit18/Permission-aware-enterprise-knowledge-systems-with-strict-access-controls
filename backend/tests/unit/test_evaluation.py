"""P18 regression tests for independent quality and security evaluation."""

from __future__ import annotations

from pathlib import Path

import pytest

from knowledge_system.evaluation.contracts import (
    GenerationObservation,
    GoldenCase,
    RetrievalObservation,
    load_golden_cases,
)
from knowledge_system.evaluation.metrics import evaluate_generation, evaluate_retrieval
from knowledge_system.evaluation.runner import regression_diff

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / "data" / "synthetic"


def _cases() -> tuple[GoldenCase, ...]:
    return load_golden_cases(DATASET / "golden-cases.json", DATASET / "manifest.json")


@pytest.mark.unit
@pytest.mark.security
def test_p18_promotes_all_golden_cases_to_complete_contract() -> None:
    cases = _cases()

    assert len(cases) == 60
    assert all(
        case.query and case.mode.value in {"INTERNAL", "CUSTOMER_SAFE"}
        for case in cases
    )
    assert all(case.forbidden_ids for case in cases)
    assert all(
        set(case.expected_citation_ids).issubset(case.expected_relevant_ids)
        for case in cases
    )
    assert {"INTERNAL", "CUSTOMER_SAFE"} == {case.mode.value for case in cases}
    assert any("cross_tenant_isolation" in case.labels for case in cases)
    assert any("indirect_prompt_injection" in case.labels for case in cases)


@pytest.mark.unit
def test_retrieval_metrics_calculate_ranked_quality_without_generation_fields() -> None:
    case = _cases()[0]
    observations = [
        RetrievalObservation(
            case_id=case.case_id,
            ranked_ids=("distractor", case.expected_relevant_ids[0]),
            allowed_ids=("distractor", case.expected_relevant_ids[0]),
            context_ids=(case.expected_relevant_ids[0],),
            tenant_by_id={
                "distractor": case.tenant_id,
                case.expected_relevant_ids[0]: case.tenant_id,
            },
            relevance_grades={case.expected_relevant_ids[0]: 3},
        )
    ]

    result = evaluate_retrieval((case,), observations, ks=(1, 2))

    assert result.recall_at_k == {"1": 0.0, "2": 1.0}
    assert result.precision_at_k == {"1": 0.0, "2": 0.5}
    assert result.mrr == 0.5
    assert result.ndcg > 0.0
    assert result.security_passed


@pytest.mark.unit
@pytest.mark.security
def test_retrieval_security_metrics_are_release_blocking() -> None:
    case = _cases()[0]
    observation = RetrievalObservation(
        case_id=case.case_id,
        ranked_ids=(),
        allowed_ids=(),
        context_ids=("secret", "harbor-contract"),
        tenant_by_id={"secret": case.tenant_id, "harbor-contract": "harbor-labs"},
        relevance_grades={},
    )

    result = evaluate_retrieval((case,), (observation,))

    assert result.unauthorized_context_rate == 1.0
    assert result.cross_tenant_leakage == 1
    assert not result.security_passed


@pytest.mark.unit
@pytest.mark.security
def test_generation_metrics_reject_unknown_citation_acceptance() -> None:
    case = _cases()[0]
    observation = GenerationObservation(
        case_id=case.case_id,
        refused=False,
        claim_keys=case.expected_claim_keys,
        citation_ids=("unknown-evidence",),
        supported_citation_ids=(),
        conflict_handled=case.expected_conflict,
        temporal_correct=True,
        warning_codes=case.expected_warning_codes,
        invalid_citation_accepted=0,
        provided_evidence_ids=case.expected_citation_ids,
    )

    result = evaluate_generation((case,), (observation,))

    assert result.invalid_citation_acceptance == 1
    assert not result.security_passed
    assert result.citation_recall == 0.0


@pytest.mark.unit
def test_regression_diff_contains_numeric_changes_only() -> None:
    previous = {"retrieval": {"mrr": 0.5}, "generation": {"citation_recall": 1.0}}
    current = {"retrieval": {"mrr": 0.25}, "generation": {"citation_recall": 1.0}}

    diff = regression_diff(previous, current)

    assert diff == {
        "available": True,
        "changes": {
            "retrieval.mrr": {"previous": 0.5, "current": 0.25},
        },
    }
