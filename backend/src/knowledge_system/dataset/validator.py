"""Deterministic validation for the synthetic demo and evaluation corpus."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import cast

from knowledge_system.evaluation.contracts import (
    EvaluationContractError,
    load_golden_cases,
)

JsonObject = dict[str, object]

_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(api[_ -]?key|access[_ -]?token|bearer)\s*[:=]\s*\S+"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
)
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_GRANTING_RELATIONS = {
    "viewer",
    "owner",
    "restricted_viewer",
    "account",
    "department",
    "project",
}
_ALLOWED_RELATIONS = {
    "tenant",
    "viewer",
    "owner",
    "restricted_viewer",
    "share_reviewer",
    "account",
    "department",
    "project",
}


def validate_text_safety(text: str) -> tuple[str, ...]:
    """Return safe-content violations without treating test wording as a secret."""

    errors: list[str] = []
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            errors.append("secret-like material detected")
            break
    if _EMAIL_PATTERN.search(text):
        errors.append("email-like PII detected")
    return tuple(errors)


def validate_dataset(dataset_root: Path) -> tuple[str, ...]:
    """Validate the complete manifest, source files, ACLs, users, and cases."""

    errors: list[str] = []
    try:
        manifest = _load_object(dataset_root / "manifest.json")
        accounts = _load_object(dataset_root / "accounts.json")
        users = _load_object(dataset_root / "users.json")
        acl = _load_object(dataset_root / "acl-fixtures.json")
        golden = _load_object(dataset_root / "golden-cases.json")
    except (OSError, ValueError) as exc:
        return (f"dataset file load failed: {exc}",)

    tenant_ids = _string_list(manifest, "tenant_ids", errors, "manifest")
    account_rows = _object_list(accounts, "accounts", errors, "accounts")
    user_rows = _object_list(users, "users", errors, "users")
    item_rows = _object_list(manifest, "source_items", errors, "manifest")
    resource_rows = _object_list(acl, "resources", errors, "acl-fixtures")
    case_rows = _object_list(golden, "cases", errors, "golden-cases")
    if golden.get("case_schema_version") != "p18-v1":
        errors.append("golden-cases.case_schema_version must be p18-v1")

    account_by_id = _index_unique(account_rows, "id", errors, "account")
    user_by_id = _index_unique(user_rows, "id", errors, "user")
    item_by_id = _index_unique(item_rows, "id", errors, "source item")
    resource_by_item = _validate_resources(
        resource_rows, item_by_id, tenant_ids, errors
    )
    _validate_accounts(account_rows, tenant_ids, errors)
    _validate_users(user_rows, tenant_ids, account_by_id, errors)

    labels: set[str] = set()
    conflict_groups: dict[str, list[JsonObject]] = defaultdict(list)
    source_types: set[str] = set()
    for item in item_rows:
        item_id = _required_string(item, "id", errors, "source item")
        source_type = _required_string(item, "source_type", errors, item_id)
        source_types.add(source_type)
        labels.update(_string_list(item, "labels", errors, item_id))
        _validate_source_item(
            item,
            item_id,
            dataset_root,
            tenant_ids,
            item_by_id,
            resource_by_item,
            errors,
        )
        profile = _object(
            item.get("evidence_profile"), errors, f"{item_id}.evidence_profile"
        )
        if profile is not None:
            group = _optional_string(profile, "conflict_group", errors, item_id)
            if group is not None:
                conflict_groups[group].append(item)

    _validate_conflict_groups(conflict_groups, errors)
    _validate_cases(case_rows, user_by_id, item_by_id, tenant_ids, labels, errors)
    try:
        promoted_cases = load_golden_cases(
            dataset_root / "golden-cases.json", dataset_root / "manifest.json"
        )
        if len(promoted_cases) < 50:
            errors.append("P18 promoted golden contract requires at least 50 cases")
    except EvaluationContractError as exc:
        errors.append(f"P18 golden contract is invalid: {exc}")

    required_labels = set(
        _string_list(manifest, "required_scenario_labels", errors, "manifest")
    )
    missing_labels = sorted(required_labels - labels)
    if missing_labels:
        errors.append(
            f"required scenario labels are missing: {', '.join(missing_labels)}"
        )
    if len(case_rows) < 50:
        errors.append(
            f"golden dataset requires at least 50 cases, found {len(case_rows)}"
        )
    required_types = {
        "document",
        "support_ticket",
        "slack_thread",
        "call_transcript",
        "policy",
    }
    missing_types = sorted(required_types - source_types)
    if missing_types:
        errors.append(f"required source types are missing: {', '.join(missing_types)}")
    if not any(
        "hourly_update" in _string_list(item, "labels", errors, "source item")
        for item in item_rows
    ):
        errors.append("hourly_update source fixture is missing")
    return tuple(errors)


def _load_object(path: Path) -> JsonObject:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return cast(JsonObject, value)


def _object(value: object, errors: list[str], field_name: str) -> JsonObject | None:
    if not isinstance(value, dict):
        errors.append(f"{field_name} must be an object")
        return None
    return cast(JsonObject, value)


def _object_list(
    row: Mapping[str, object], key: str, errors: list[str], field_name: str
) -> list[JsonObject]:
    value = row.get(key)
    if not isinstance(value, list):
        errors.append(f"{field_name}.{key} must be a list")
        return []
    result: list[JsonObject] = []
    for index, item in enumerate(value):
        parsed = _object(item, errors, f"{field_name}.{key}[{index}]")
        if parsed is not None:
            result.append(parsed)
    return result


def _string_list(
    row: Mapping[str, object], key: str, errors: list[str], field_name: str
) -> list[str]:
    value = row.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        errors.append(f"{field_name}.{key} must be a list of strings")
        return []
    return [item for item in value if isinstance(item, str)]


def _required_string(
    row: Mapping[str, object], key: str, errors: list[str], field_name: str
) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field_name}.{key} must be a non-empty string")
        return ""
    return value


def _optional_string(
    row: Mapping[str, object], key: str, errors: list[str], field_name: str
) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append(f"{field_name}.{key} must be a string or null")
        return None
    return value


def _required_int(
    row: Mapping[str, object], key: str, errors: list[str], field_name: str
) -> int:
    value = row.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        errors.append(f"{field_name}.{key} must be an integer")
        return 0
    return value


def _index_unique(
    rows: Sequence[JsonObject], key: str, errors: list[str], kind: str
) -> dict[str, JsonObject]:
    indexed: dict[str, JsonObject] = {}
    for index, row in enumerate(rows):
        value = _required_string(row, key, errors, f"{kind}[{index}]")
        if value in indexed:
            errors.append(f"duplicate {kind} ID: {value}")
        indexed[value] = row
    return indexed


def _validate_accounts(
    rows: Sequence[JsonObject], tenant_ids: Sequence[str], errors: list[str]
) -> None:
    for index, row in enumerate(rows):
        field_name = f"account[{index}]"
        tenant_id = _required_string(row, "tenant_id", errors, field_name)
        if tenant_id not in tenant_ids:
            errors.append(f"{field_name} references unknown tenant {tenant_id}")
        if row.get("synthetic") is not True:
            errors.append(f"{field_name} must be explicitly synthetic")


def _validate_users(
    rows: Sequence[JsonObject],
    tenant_ids: Sequence[str],
    account_by_id: Mapping[str, JsonObject],
    errors: list[str],
) -> None:
    for index, row in enumerate(rows):
        field_name = f"user[{index}]"
        tenant_id = _required_string(row, "tenant_id", errors, field_name)
        if tenant_id not in tenant_ids:
            errors.append(f"{field_name} references unknown tenant {tenant_id}")
        account_ids = _string_list(row, "account_ids", errors, field_name)
        for account_id in account_ids:
            account = account_by_id.get(account_id)
            if account is None:
                errors.append(f"{field_name} references unknown account {account_id}")
            elif account.get("tenant_id") != tenant_id:
                errors.append(
                    f"{field_name} crosses tenant through account {account_id}"
                )
        for key in ("subject_id", "role", "department"):
            _required_string(row, key, errors, field_name)
        _string_list(row, "groups", errors, field_name)


def _validate_source_item(
    item: JsonObject,
    item_id: str,
    dataset_root: Path,
    tenant_ids: Sequence[str],
    item_by_id: Mapping[str, JsonObject],
    resource_by_item: Mapping[str, JsonObject],
    errors: list[str],
) -> None:
    tenant_id = _required_string(item, "tenant_id", errors, item_id)
    if tenant_id not in tenant_ids:
        errors.append(f"{item_id} references unknown tenant {tenant_id}")
    path_value = _required_string(item, "source_path", errors, item_id)
    source_path = dataset_root / path_value
    try:
        source_path.resolve().relative_to(dataset_root.resolve())
    except ValueError:
        errors.append(f"{item_id} source path escapes the dataset root")
        return
    hash_value = _required_string(item, "content_hash", errors, item_id)
    try:
        content = source_path.read_bytes()
    except OSError as exc:
        errors.append(f"{item_id} source file cannot be read: {exc}")
        content = b""
    actual_hash = f"sha256:{sha256(content).hexdigest()}"
    if hash_value != actual_hash:
        errors.append(f"{item_id} content hash does not match source file")
    text = content.decode("utf-8", errors="replace")
    for violation in validate_text_safety(text):
        errors.append(f"{item_id}: {violation}")
    if source_path.suffix.lower() == ".json":
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            errors.append(f"{item_id} JSON source is invalid: {exc.msg}")

    classification = _required_string(item, "classification", errors, item_id)
    if classification not in {
        "PUBLIC",
        "CUSTOMER_SHAREABLE",
        "INTERNAL",
        "CONFIDENTIAL",
        "RESTRICTED",
    }:
        errors.append(f"{item_id} has an unknown classification")
    if item.get("external_shareable") is True and classification not in {
        "PUBLIC",
        "CUSTOMER_SHAREABLE",
    }:
        errors.append(f"{item_id} is externally shareable but not shareable-classified")
    status = _required_string(item, "status", errors, item_id)
    deleted_at = item.get("deleted_at")
    if status == "DELETED" and not isinstance(deleted_at, str):
        errors.append(f"{item_id} deleted fixture requires deleted_at")
    if status == "ACTIVE" and deleted_at is not None:
        errors.append(f"{item_id} active fixture cannot have deleted_at")
    if status == "DELETED" and resource_by_item.get(item_id, {}).get("tuples"):
        tuples = resource_by_item[item_id].get("tuples")
        if isinstance(tuples, list) and any(
            isinstance(value, dict) and value.get("relation") in _GRANTING_RELATIONS
            for value in tuples
        ):
            errors.append(f"{item_id} deleted fixture has a granting ACL tuple")
    for relation_key in ("supersedes", "superseded_by"):
        relation_id = item.get(relation_key)
        if relation_id is not None and (
            not isinstance(relation_id, str) or relation_id not in item_by_id
        ):
            errors.append(f"{item_id}.{relation_key} references an unknown source item")
    profile = _object(
        item.get("evidence_profile"), errors, f"{item_id}.evidence_profile"
    )
    if profile is not None:
        rank = _required_int(profile, "authority_rank", errors, item_id)
        if rank < 0:
            errors.append(f"{item_id} authority rank cannot be negative")
        _required_string(profile, "effective_at", errors, item_id)
        _required_string(profile, "freshness_class", errors, item_id)
        if not isinstance(profile.get("is_current"), bool):
            errors.append(f"{item_id}.evidence_profile.is_current must be boolean")
    if item.get("update_cadence_minutes") is not None:
        cadence = _required_int(item, "update_cadence_minutes", errors, item_id)
        if cadence != 60:
            errors.append(f"{item_id} hourly fixture cadence must be 60 minutes")


def _validate_resources(
    rows: Sequence[JsonObject],
    item_by_id: Mapping[str, JsonObject],
    tenant_ids: Sequence[str],
    errors: list[str],
) -> dict[str, JsonObject]:
    resource_by_item: dict[str, JsonObject] = {}
    resource_ids: set[str] = set()
    for index, row in enumerate(rows):
        field_name = f"acl resource[{index}]"
        resource_id = _required_string(row, "resource_id", errors, field_name)
        item_id = _required_string(row, "source_item_id", errors, field_name)
        tenant_id = _required_string(row, "tenant_id", errors, field_name)
        if resource_id in resource_ids:
            errors.append(f"duplicate ACL resource ID: {resource_id}")
        resource_ids.add(resource_id)
        if item_id not in item_by_id:
            errors.append(f"{field_name} references unknown source item {item_id}")
        elif item_by_id[item_id].get("tenant_id") != tenant_id:
            errors.append(f"{field_name} crosses tenant for {item_id}")
        if tenant_id not in tenant_ids:
            errors.append(f"{field_name} references unknown tenant {tenant_id}")
        tuples = row.get("tuples")
        if not isinstance(tuples, list):
            errors.append(f"{field_name}.tuples must be a list")
            continue
        if item_id in resource_by_item:
            errors.append(f"duplicate ACL mapping for source item {item_id}")
        resource_by_item[item_id] = row
        for tuple_index, value in enumerate(tuples):
            tuple_row = _object(value, errors, f"{field_name}.tuples[{tuple_index}]")
            if tuple_row is None:
                continue
            user = _required_string(tuple_row, "user", errors, field_name)
            relation = _required_string(tuple_row, "relation", errors, field_name)
            object_id = _required_string(tuple_row, "object", errors, field_name)
            if relation not in _ALLOWED_RELATIONS:
                errors.append(
                    f"{field_name} has unsupported OpenFGA relation {relation}"
                )
            if object_id != resource_id:
                errors.append(f"{field_name} tuple object does not match resource_id")
            if not (
                user.startswith(
                    ("user:", "group:", "account:", "department:", "tenant:")
                )
            ):
                errors.append(
                    f"{field_name} tuple user is not a namespaced OpenFGA subject"
                )
    if set(resource_by_item) != set(item_by_id):
        errors.append("ACL fixture must map exactly one resource to every source item")
    return resource_by_item


def _validate_conflict_groups(
    groups: Mapping[str, Sequence[JsonObject]], errors: list[str]
) -> None:
    for group_name, items in groups.items():
        current_items: list[JsonObject] = []
        authority_ranks: list[int] = []
        for item in items:
            profile = item.get("evidence_profile")
            if not isinstance(profile, dict):
                continue
            rank = profile.get("authority_rank")
            if isinstance(rank, int) and not isinstance(rank, bool):
                authority_ranks.append(rank)
            if profile.get("is_current") is True:
                current_items.append(item)
        highest_rank = max(authority_ranks, default=-1)
        authoritative_current: list[JsonObject] = []
        for item in current_items:
            profile = item.get("evidence_profile")
            if (
                isinstance(profile, dict)
                and profile.get("authority_rank") == highest_rank
            ):
                authoritative_current.append(item)
        if len(authoritative_current) != 1:
            errors.append(
                f"conflict group {group_name} must have exactly one current highest-authority item"
            )


def _validate_cases(
    rows: Sequence[JsonObject],
    user_by_id: Mapping[str, JsonObject],
    item_by_id: Mapping[str, JsonObject],
    tenant_ids: Sequence[str],
    labels: set[str],
    errors: list[str],
) -> None:
    case_ids: set[str] = set()
    for index, case in enumerate(rows):
        field_name = f"case[{index}]"
        case_id = _required_string(case, "id", errors, field_name)
        if case_id in case_ids:
            errors.append(f"duplicate case ID: {case_id}")
        case_ids.add(case_id)
        _required_string(case, "question", errors, field_name)
        principal = _required_string(case, "principal", errors, field_name)
        tenant_id = _required_string(case, "tenant_id", errors, field_name)
        user = user_by_id.get(principal)
        if user is None:
            errors.append(f"{field_name} references unknown principal {principal}")
        elif user.get("tenant_id") != tenant_id:
            errors.append(f"{field_name} principal tenant does not match case tenant")
        if tenant_id not in tenant_ids:
            errors.append(f"{field_name} references unknown tenant {tenant_id}")
        case_labels = _string_list(case, "labels", errors, field_name)
        labels.update(case_labels)
        evidence_ids = _string_list(case, "expected_evidence_ids", errors, field_name)
        expected_refusal = case.get("expected_refusal")
        if not isinstance(expected_refusal, bool):
            errors.append(f"{field_name}.expected_refusal must be boolean")
        if expected_refusal is True and evidence_ids:
            errors.append(f"{field_name} refusal must not contain expected evidence")
        if expected_refusal is False and not evidence_ids:
            errors.append(f"{field_name} answer must contain expected evidence")
        for evidence_id in evidence_ids:
            item = item_by_id.get(evidence_id)
            if item is None:
                errors.append(f"{field_name} references unknown evidence {evidence_id}")
            elif item.get("tenant_id") != tenant_id:
                errors.append(f"{field_name} references cross-tenant evidence")
            elif item.get("status") == "DELETED":
                errors.append(f"{field_name} references deleted evidence {evidence_id}")
        _required_string(case, "expected_retrieval_outcome", errors, field_name)
        _required_string(case, "authority_expectation", errors, field_name)
        _required_string(case, "freshness_expectation", errors, field_name)
        for forbidden_key in ("answer", "expected_answer", "model_answer"):
            if forbidden_key in case:
                errors.append(f"{field_name} must not store runtime model answers")


def main() -> int:
    root = Path(__file__).resolve().parents[4] / "data" / "synthetic"
    errors = validate_dataset(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"Synthetic dataset validation passed: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
