"""Command-line entry point for the local P18 evaluation harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from knowledge_system.evaluation.contracts import (
    GenerationObservation,
    RetrievalObservation,
    load_golden_cases,
)
from knowledge_system.evaluation.runner import (
    EvaluationGateError,
    fixture_observations,
    load_observations,
    run_evaluation,
    write_reports,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic P18 evaluations")
    parser.add_argument("--output-dir", type=Path, default=Path("reports/evals/1.0.0"))
    parser.add_argument("--retrieval-observations", type=Path)
    parser.add_argument("--generation-observations", type=Path)
    parser.add_argument("--previous-report", type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[4]
    dataset_root = root / "data" / "synthetic"
    cases = load_golden_cases(
        dataset_root / "golden-cases.json", dataset_root / "manifest.json"
    )
    dataset_version = _dataset_version(dataset_root / "golden-cases.json")
    if bool(args.retrieval_observations) != bool(args.generation_observations):
        parser.error("retrieval and generation observations must be supplied together")
    if args.retrieval_observations and args.generation_observations:
        retrieval = tuple(
            RetrievalObservation.from_json(row)
            for row in load_observations(args.retrieval_observations, "retrieval")
        )
        generation = tuple(
            GenerationObservation.from_json(row)
            for row in load_observations(args.generation_observations, "generation")
        )
        baseline_kind = "observed_pipeline"
    else:
        retrieval, generation = fixture_observations(cases)
        baseline_kind = "contract_fixture_smoke"

    previous = None
    if args.previous_report:
        previous = _load_mapping(args.previous_report)
    report = run_evaluation(
        cases,
        retrieval,
        generation,
        dataset_version=dataset_version,
        baseline_kind=baseline_kind,
    )
    try:
        write_reports(report, args.output_dir, previous_report=previous)
    except EvaluationGateError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"P18 evaluation passed: {len(cases)} cases -> {args.output_dir}")
    return 0


def _dataset_version(path: Path) -> str:
    payload = _load_mapping(path)
    value = payload.get("dataset_version")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("dataset_version is required")
    return value


def _load_mapping(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON object required: {path}")
    return cast(dict[str, object], value)


if __name__ == "__main__":
    raise SystemExit(main())
