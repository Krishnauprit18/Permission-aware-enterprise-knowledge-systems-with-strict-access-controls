"""Typed P18 dataset and observation contracts.

The checked-in P08 case records remain concise. ``GoldenCase.from_json``
promotes every record to the complete P18 contract using only deterministic
labels and trusted fixture metadata; no model answer text is introduced.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from knowledge_system.domain.policy import AnswerMode, PolicyWarningCode

JsonObject = dict[str, object]


class EvaluationContractError(ValueError):
    """A golden case or observed evaluation record is malformed."""


class EvaluationRunKind(StrEnum):
    RETRIEVAL = "retrieval"
    GENERATION = "generation"


@dataclass(frozen=True, slots=True)
class GoldenCase:
    """One complete, answer-text-free golden evaluation case."""

    case_id: str
    principal: str
    tenant_id: str
    query: str
    mode: AnswerMode
    labels: tuple[str, ...]
    expected_relevant_ids: tuple[str, ...]
    forbidden_ids: tuple[str, ...]
    expected_claim_keys: tuple[str, ...]
    expected_citation_ids: tuple[str, ...]
    expected_refusal: bool
    expected_conflict: bool
    expected_warning_codes: tuple[str, ...]
    authority_expectation: str
    freshness_expectation: str

    @classmethod
    def from_json(
        cls,
        row: Mapping[str, object],
        *,
        all_item_ids: Sequence[str],
        item_tenants: Mapping[str, str],
        legal_only_ids: Sequence[str],
        item_shareable: Mapping[str, bool],
    ) -> GoldenCase:
        case_id = _required_string(row, "id")
        labels = _string_tuple(row, "labels")
        expected = _string_tuple(row, "expected_evidence_ids")
        expected_refusal = _required_bool(row, "expected_refusal")
        tenant_id = _required_string(row, "tenant_id")
        principal = _required_string(row, "principal")
        mode_value = row.get("mode")
        mode = (
            AnswerMode(mode_value)
            if isinstance(mode_value, str)
            else AnswerMode.CUSTOMER_SAFE
            if "customer_safe" in labels
            else AnswerMode.INTERNAL
        )
        forbidden = _string_tuple(row, "forbidden_ids")
        if not forbidden:
            forbidden = tuple(
                item_id
                for item_id in all_item_ids
                if item_tenants.get(item_id) != tenant_id
                or (item_id in legal_only_ids and principal != "leah-legal-counsel")
                or (
                    mode is AnswerMode.CUSTOMER_SAFE
                    and not item_shareable.get(item_id, False)
                )
            )
        claims = _string_tuple(row, "expected_claim_keys")
        if not claims:
            claims = _claim_keys(labels, expected_refusal)
        citations = _string_tuple(row, "expected_citation_ids")
        if not citations:
            citations = (
                expected
                if mode is AnswerMode.INTERNAL
                else tuple(
                    item_id
                    for item_id in expected
                    if item_shareable.get(item_id, False)
                )
            )
        warning_codes = _string_tuple(row, "expected_warning_codes")
        if not warning_codes:
            warning_codes = _warning_codes(labels, mode)
        return cls(
            case_id=case_id,
            principal=principal,
            tenant_id=tenant_id,
            query=_required_string(row, "question"),
            mode=mode,
            labels=labels,
            expected_relevant_ids=expected,
            forbidden_ids=forbidden,
            expected_claim_keys=claims,
            expected_citation_ids=citations,
            expected_refusal=expected_refusal,
            expected_conflict=(
                "conflicting_evidence" in labels
                or "mixed_conflict" in _optional_string(row, "freshness_expectation")
            ),
            expected_warning_codes=warning_codes,
            authority_expectation=_required_string(row, "authority_expectation"),
            freshness_expectation=_required_string(row, "freshness_expectation"),
        )


@dataclass(frozen=True, slots=True)
class RetrievalObservation:
    """Text-free output from one retrieval execution."""

    case_id: str
    ranked_ids: tuple[str, ...]
    allowed_ids: tuple[str, ...]
    context_ids: tuple[str, ...]
    tenant_by_id: Mapping[str, str]
    relevance_grades: Mapping[str, int]

    @classmethod
    def from_json(cls, row: Mapping[str, object]) -> RetrievalObservation:
        ranked = _string_tuple(row, "ranked_ids")
        allowed = _string_tuple(row, "allowed_ids")
        context = _string_tuple(row, "context_ids")
        tenant_value = row.get("tenant_by_id", {})
        if not isinstance(tenant_value, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in tenant_value.items()
        ):
            raise EvaluationContractError("tenant_by_id must be a string map")
        grades_value = row.get("relevance_grades", {})
        if not isinstance(grades_value, dict) or any(
            not isinstance(key, str)
            or not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for key, value in grades_value.items()
        ):
            raise EvaluationContractError(
                "relevance_grades must be a non-negative integer map"
            )
        return cls(
            case_id=_required_string(row, "case_id"),
            ranked_ids=ranked,
            allowed_ids=allowed,
            context_ids=context,
            tenant_by_id=cast(Mapping[str, str], tenant_value),
            relevance_grades=cast(Mapping[str, int], grades_value),
        )


@dataclass(frozen=True, slots=True)
class GenerationObservation:
    """Answer metadata used by deterministic generation evaluation."""

    case_id: str
    refused: bool
    claim_keys: tuple[str, ...]
    citation_ids: tuple[str, ...]
    supported_citation_ids: tuple[str, ...]
    conflict_handled: bool
    temporal_correct: bool
    warning_codes: tuple[str, ...]
    invalid_citation_accepted: int
    provided_evidence_ids: tuple[str, ...]

    @classmethod
    def from_json(cls, row: Mapping[str, object]) -> GenerationObservation:
        invalid = row.get("invalid_citation_accepted", 0)
        if not isinstance(invalid, int) or isinstance(invalid, bool) or invalid < 0:
            raise EvaluationContractError(
                "invalid_citation_accepted must be non-negative"
            )
        return cls(
            case_id=_required_string(row, "case_id"),
            refused=_required_bool(row, "refused"),
            claim_keys=_string_tuple(row, "claim_keys"),
            citation_ids=_string_tuple(row, "citation_ids"),
            supported_citation_ids=_string_tuple(row, "supported_citation_ids"),
            conflict_handled=_required_bool(row, "conflict_handled"),
            temporal_correct=_required_bool(row, "temporal_correct"),
            warning_codes=_string_tuple(row, "warning_codes"),
            invalid_citation_accepted=invalid,
            provided_evidence_ids=_string_tuple(row, "provided_evidence_ids"),
        )


def load_golden_cases(path: Path, manifest_path: Path) -> tuple[GoldenCase, ...]:
    """Load and promote the versioned synthetic case file."""

    payload = _load_object(path)
    manifest = _load_object(manifest_path)
    rows = payload.get("cases")
    items = manifest.get("source_items")
    if not isinstance(rows, list) or not isinstance(items, list):
        raise EvaluationContractError("golden cases and manifest items must be lists")
    item_rows = [item for item in items if isinstance(item, dict)]
    ids = tuple(_required_string(item, "id") for item in item_rows)
    tenants = {
        _required_string(item, "id"): _required_string(item, "tenant_id")
        for item in item_rows
    }
    shareable = {
        _required_string(item, "id"): item.get("external_shareable") is True
        for item in item_rows
    }
    legal_only = tuple(
        _required_string(item, "id")
        for item in item_rows
        if "legal_only" in _string_tuple(item, "labels")
    )
    cases = tuple(
        GoldenCase.from_json(
            item,
            all_item_ids=ids,
            item_tenants=tenants,
            legal_only_ids=legal_only,
            item_shareable=shareable,
        )
        for item in rows
        if isinstance(item, dict)
    )
    if len(cases) != len(rows) or len({case.case_id for case in cases}) != len(cases):
        raise EvaluationContractError("golden cases must be objects with unique IDs")
    return cases


def _claim_keys(labels: Sequence[str], refusal: bool) -> tuple[str, ...]:
    if refusal:
        return ()
    mapping = (
        ("current_authoritative_approved_date", "approved_date"),
        ("old_customer_statement", "historical_august_statement"),
        ("later_internal_tentative", "tentative_september"),
        ("informal_engineering_concern", "engineering_concern_is_not_approval"),
        ("customer_safe", "external_shareability_enforced"),
        ("role_revocation", "revocation_effective_next_query"),
        ("deletion", "deleted_content_excluded"),
        ("indirect_prompt_injection", "retrieved_instructions_untrusted"),
        ("cross_document_synthesis", "cross_document_synthesis"),
    )
    return tuple(key for label, key in mapping if label in labels) or (
        "supported_facts",
    )


def _warning_codes(labels: Sequence[str], mode: AnswerMode) -> tuple[str, ...]:
    if mode is AnswerMode.CUSTOMER_SAFE:
        return (PolicyWarningCode.CUSTOMER_SAFE_POLICY_APPLIED.value,)
    codes: list[str] = []
    if "legal_only" in labels:
        codes.append(PolicyWarningCode.RESTRICTED_CONTENT_PRESENT.value)
    elif "internal_not_customer_shareable" in labels:
        codes.append(PolicyWarningCode.INTERNAL_CONTENT_PRESENT.value)
    return tuple(codes)


def _load_object(path: Path) -> JsonObject:
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvaluationContractError(f"cannot load evaluation data: {path}") from exc
    if not isinstance(value, dict):
        raise EvaluationContractError(f"evaluation data must be an object: {path}")
    return cast(JsonObject, value)


def _required_string(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvaluationContractError(f"{key} must be a non-empty string")
    return value


def _required_bool(row: Mapping[str, object], key: str) -> bool:
    value = row.get(key)
    if not isinstance(value, bool):
        raise EvaluationContractError(f"{key} must be boolean")
    return value


def _optional_string(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    return value if isinstance(value, str) else ""


def _string_tuple(row: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = row.get(key, ())
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise EvaluationContractError(f"{key} must be a sequence of strings")
    return tuple(value)
