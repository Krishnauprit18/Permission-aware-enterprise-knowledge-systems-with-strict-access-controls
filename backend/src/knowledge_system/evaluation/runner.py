"""Run and serialize the local P18 evaluation contract."""

from __future__ import annotations

import html
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from knowledge_system.evaluation.contracts import (
    GenerationObservation,
    GoldenCase,
    RetrievalObservation,
)
from knowledge_system.evaluation.metrics import (
    evaluate_generation,
    evaluate_retrieval,
)


def fixture_observations(
    cases: Sequence[GoldenCase],
) -> tuple[tuple[RetrievalObservation, ...], tuple[GenerationObservation, ...]]:
    """Create a safe contract smoke baseline without storing answer text.

    This is intentionally an oracle-shaped fixture, not a product-quality
    retrieval benchmark. Real runs replace these observations with records from
    the protected application pipeline.
    """

    retrieval: list[RetrievalObservation] = []
    generation: list[GenerationObservation] = []
    for case in cases:
        allowed = case.expected_relevant_ids
        retrieval.append(
            RetrievalObservation(
                case_id=case.case_id,
                ranked_ids=case.expected_relevant_ids,
                allowed_ids=allowed,
                context_ids=(
                    ()
                    if case.expected_refusal
                    else tuple(
                        item_id
                        for item_id in allowed
                        if item_id not in case.forbidden_ids
                    )
                ),
                tenant_by_id=dict.fromkeys(allowed, case.tenant_id),
                relevance_grades=dict.fromkeys(allowed, 3),
            )
        )
        generation.append(
            GenerationObservation(
                case_id=case.case_id,
                refused=case.expected_refusal,
                claim_keys=case.expected_claim_keys,
                citation_ids=case.expected_citation_ids,
                supported_citation_ids=case.expected_citation_ids,
                conflict_handled=case.expected_conflict,
                temporal_correct=True,
                warning_codes=case.expected_warning_codes,
                invalid_citation_accepted=0,
                provided_evidence_ids=case.expected_citation_ids,
            )
        )
    return tuple(retrieval), tuple(generation)


def load_observations(path: Path, kind: str) -> tuple[Mapping[str, object], ...]:
    """Load a JSON array of text-free observations supplied by a real run."""

    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot load {kind} observations: {path}") from exc
    if not isinstance(payload, list) or any(
        not isinstance(item, dict) for item in payload
    ):
        raise ValueError(f"{kind} observations must be a JSON array of objects")
    return tuple(cast(Mapping[str, object], item) for item in payload)


def run_evaluation(
    cases: Sequence[GoldenCase],
    retrieval: Sequence[RetrievalObservation],
    generation: Sequence[GenerationObservation],
    *,
    dataset_version: str,
    baseline_kind: str,
) -> dict[str, object]:
    """Evaluate independent streams and return a JSON-safe report object."""

    retrieval_result = evaluate_retrieval(cases, retrieval)
    generation_result = evaluate_generation(cases, generation)
    return {
        "schema_version": "p18-evaluation-v1",
        "dataset_version": dataset_version,
        "baseline_kind": baseline_kind,
        "case_count": len(cases),
        "security": {
            "unauthorized_context_rate": retrieval_result.unauthorized_context_rate,
            "cross_tenant_leakage": retrieval_result.cross_tenant_leakage,
            "invalid_citation_acceptance": generation_result.invalid_citation_acceptance,
            "release_blocking": not (
                retrieval_result.security_passed and generation_result.security_passed
            ),
        },
        "retrieval": retrieval_result.as_dict(),
        "generation": generation_result.as_dict(),
    }


def write_reports(
    report: Mapping[str, object],
    output_dir: Path,
    *,
    previous_report: Mapping[str, object] | None = None,
) -> None:
    """Write versioned JSON, Markdown, HTML, and numeric regression diff."""

    output_dir.mkdir(parents=True, exist_ok=True)
    retrieval = _mapping(report["retrieval"])
    generation = _mapping(report["generation"])
    security = _mapping(report["security"])
    _write_json(output_dir / "summary.json", report)
    _write_json(output_dir / "retrieval.json", retrieval)
    _write_json(output_dir / "generation.json", generation)
    diff = regression_diff(previous_report, report)
    _write_json(output_dir / "regression-diff.json", diff)
    markdown = _markdown_report(report, diff)
    (output_dir / "summary.md").write_text(markdown, encoding="utf-8")
    (output_dir / "summary.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>P18 evaluation</title>'
        f"<pre>{html.escape(markdown)}</pre>",
        encoding="utf-8",
    )
    if bool(security["release_blocking"]):
        raise EvaluationGateError("security evaluation metric is non-zero")


class EvaluationGateError(RuntimeError):
    """The evaluation produced a release-blocking security result."""


def regression_diff(
    previous: Mapping[str, object] | None, current: Mapping[str, object]
) -> dict[str, object]:
    """Compare numeric metrics only; never diff source text or model output."""

    if previous is None:
        return {"available": False, "changes": {}}
    old_values = _numeric_metrics(previous)
    new_values = _numeric_metrics(current)
    keys = sorted(set(old_values) | set(new_values))
    return {
        "available": True,
        "changes": {
            key: {"previous": old_values.get(key), "current": new_values.get(key)}
            for key in keys
            if old_values.get(key) != new_values.get(key)
        },
    }


def _numeric_metrics(value: Mapping[str, object]) -> dict[str, float]:
    result: dict[str, float] = {}
    for section_name in ("retrieval", "generation", "security"):
        section = value.get(section_name)
        if not isinstance(section, dict):
            continue
        for name, metric in section.items():
            if isinstance(metric, (int, float)) and not isinstance(metric, bool):
                result[f"{section_name}.{name}"] = float(metric)
            elif isinstance(metric, dict):
                for child_name, child in metric.items():
                    if isinstance(child, (int, float)) and not isinstance(child, bool):
                        result[f"{section_name}.{name}.{child_name}"] = float(child)
    return result


def _markdown_report(report: Mapping[str, object], diff: Mapping[str, object]) -> str:
    retrieval = _mapping(report["retrieval"])
    generation = _mapping(report["generation"])
    security = _mapping(report["security"])
    lines = [
        "# P18 Evaluation Report",
        "",
        f"- Dataset: `{report['dataset_version']}`",
        f"- Cases: `{report['case_count']}`",
        f"- Baseline: `{report['baseline_kind']}`",
        "",
        "## Retrieval",
        "",
        f"- Recall@K: `{retrieval['recall_at_k']}`",
        f"- Precision@K: `{retrieval['precision_at_k']}`",
        f"- MRR: `{retrieval['mrr']}`",
        f"- nDCG: `{retrieval['ndcg']}`",
        "",
        "## Generation",
        "",
        f"- Grounded correctness: `{generation['grounded_correctness']}`",
        f"- Citation precision/recall/support: `{generation['citation_precision']}` / `{generation['citation_recall']}` / `{generation['citation_support']}`",
        f"- Conflict/temporal/refusal/warning: `{generation['conflict_handling']}` / `{generation['temporal_correctness']}` / `{generation['refusal_correctness']}` / `{generation['warning_correctness']}`",
        "",
        "## Security Gates",
        "",
        f"- Unauthorized Context Rate: `{security['unauthorized_context_rate']}`",
        f"- Cross-Tenant Leakage: `{security['cross_tenant_leakage']}`",
        f"- Invalid Citation Acceptance: `{security['invalid_citation_acceptance']}`",
        f"- Release-blocking: `{security['release_blocking']}`",
        "",
        "## Regression",
        "",
        f"- Diff available: `{diff['available']}`",
        f"- Changed numeric metrics: `{len(_mapping(diff['changes']))}`",
        "",
        "This report contains identifiers and metrics only; it contains no source text, model answer, vector, or chain-of-thought.",
    ]
    return "\n".join(lines) + "\n"


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("evaluation report section must be an object")
    return cast(dict[str, object], value)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def utc_report_timestamp() -> str:
    """Provide an explicit UTC timestamp for callers that need run identity."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
