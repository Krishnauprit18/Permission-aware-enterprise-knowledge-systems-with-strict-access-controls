"""Safe, deterministic connectors for the checked-in synthetic source fixtures."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast

from knowledge_system.application.ports.ingestion import ConnectorResult
from knowledge_system.domain.ingestion import (
    AclRelationshipIntent,
    ConnectorFailure,
    RawAttachment,
    SourceEnvelope,
)
from knowledge_system.domain.persistence import (
    AccountId,
    Classification,
    DocumentId,
    DocumentMetadata,
    TenantId,
)

JsonObject = dict[str, object]
_ALLOWED_SUFFIXES = {
    "document": {".md": "text/markdown"},
    "support_ticket": {".json": "application/json"},
    "slack_thread": {".json": "application/json"},
    "call_transcript": {".json": "application/json"},
}


class FixtureCatalog:
    """Read only the manifest-selected files beneath one trusted fixture root."""

    def __init__(self, root: Path, *, max_bytes: int = 1_048_576) -> None:
        if max_bytes < 1:
            raise ValueError("fixture file limit must be positive")
        self._root = root.resolve()
        self._max_bytes = max_bytes
        manifest = self._load_object(self._root / "manifest.json")
        acl = self._load_object(self._root / "acl-fixtures.json")
        self._items = self._object_list(manifest, "source_items")
        self._acl_by_item = self._build_acl_index(acl)
        self._duplicate_source_ids = self._find_duplicate_source_ids(self._items)

    def changes(
        self, source_type: str, checkpoint: str | None
    ) -> Iterable[ConnectorResult]:
        """Yield only source-type changes after the supplied ordinal cursor."""

        rows = [row for row in self._items if row.get("source_type") == source_type]
        start = self._checkpoint_ordinal(source_type, checkpoint)
        for ordinal, row in enumerate(rows, start=1):
            cursor = f"{source_type}:{ordinal}"
            if ordinal <= start:
                continue
            yield self._to_change(row, cursor, source_type)

    def _to_change(
        self, row: JsonObject, cursor: str, source_type: str
    ) -> ConnectorResult:
        raw_item_id = row.get("id")
        item_id = (
            raw_item_id
            if isinstance(raw_item_id, str) and raw_item_id.strip()
            else f"invalid-item-{sha256(cursor.encode('utf-8')).hexdigest()[:16]}"
        )
        try:
            item_id = self._required_string(row, "id")
            if self._required_string(row, "source_type") != source_type:
                raise ValueError("source type does not match connector")
            source_external_id = self._required_string(row, "source_external_id")
            duplicate_key = (
                self._required_string(row, "tenant_id"),
                source_type,
                source_external_id,
            )
            if duplicate_key in self._duplicate_source_ids:
                raise ValueError("duplicate source external identity")
            path_value = self._required_string(row, "source_path")
            source_path = self._safe_source_path(path_value)
            suffix = source_path.suffix.lower()
            content_type = _ALLOWED_SUFFIXES[source_type][suffix]
            payload = self._read_bounded(source_path)
            self._validate_payload(payload, source_type)
            expected_hash = self._required_string(row, "content_hash")
            actual_hash = f"sha256:{sha256(payload).hexdigest()}"
            if actual_hash != expected_hash:
                raise ValueError("source content hash does not match manifest")
            metadata = self._metadata(row)
            acl = self._acl_by_item[item_id]
            attachments = self._attachments(payload, source_type)
            supersedes = row.get("supersedes")
            if supersedes is not None and not isinstance(supersedes, str):
                raise TypeError("supersedes must be a string or null")
            return SourceEnvelope(
                document_id=DocumentId(item_id),
                metadata=metadata,
                external_cursor=cursor,
                raw_content=payload,
                acl_relationships=acl,
                attachments=attachments,
                source_path=path_value,
                is_deleted=row.get("status") == "DELETED",
                content_type=content_type,
                supersedes_document_id=(
                    DocumentId(supersedes) if supersedes is not None else None
                ),
            )
        except (KeyError, TypeError, ValueError, OSError):
            return ConnectorFailure(
                document_id=item_id,
                external_cursor=cursor,
                error_code="MALFORMED_SOURCE_RECORD",
                permanent=True,
            )

    def _metadata(self, row: JsonObject) -> DocumentMetadata:
        account_ids = tuple(
            AccountId(value) for value in self._string_list(row, "account_ids")
        )
        supersedes = row.get("supersedes")
        if supersedes is not None and not isinstance(supersedes, str):
            raise TypeError("supersedes must be a string or null")
        return DocumentMetadata(
            source_type=self._required_string(row, "source_type"),
            source_external_id=self._required_string(row, "source_external_id"),
            source_url=self._optional_string(row, "source_url"),
            tenant_id=TenantId(self._required_string(row, "tenant_id")),
            account_ids=account_ids,
            department=self._optional_string(row, "department"),
            created_at=self._timestamp(row, "created_at"),
            updated_at=self._timestamp(row, "updated_at"),
            author=self._optional_string(row, "author"),
            classification=Classification(self._required_string(row, "classification")),
            external_shareable=self._required_bool(row, "external_shareable"),
            authority_level=self._required_int(row, "authority_level"),
            acl_relationship_refs=tuple(
                self._string_list(row, "acl_relationship_refs")
            ),
            version=self._required_int(row, "version"),
            content_hash=self._required_string(row, "content_hash"),
            language=self._required_string(row, "language"),
        )

    def _attachments(
        self, payload: bytes, source_type: str
    ) -> tuple[RawAttachment, ...]:
        if source_type not in {"support_ticket", "slack_thread", "call_transcript"}:
            return ()
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict):
            raise TypeError("source JSON must be an object")
        refs = value.get("attachment_refs", [])
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            raise TypeError("attachment_refs must be a list of strings")
        return tuple(
            RawAttachment(
                name=ref, external_ref=ref, media_type="application/octet-stream"
            )
            for ref in cast(Sequence[str], refs)
        )

    def _validate_payload(self, payload: bytes, source_type: str) -> None:
        if source_type not in {"support_ticket", "slack_thread", "call_transcript"}:
            return
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict):
            raise TypeError("source JSON must be an object")

    def _safe_source_path(self, path_value: str) -> Path:
        candidate = (self._root / path_value).resolve()
        candidate.relative_to(self._root)
        suffix = candidate.suffix.lower()
        if suffix not in {
            suffix for types in _ALLOWED_SUFFIXES.values() for suffix in types
        }:
            raise ValueError("source file type is not allowed")
        if not candidate.is_file():
            raise OSError("source fixture is not a regular file")
        return candidate

    def _read_bounded(self, path: Path) -> bytes:
        with path.open("rb") as handle:
            payload = handle.read(self._max_bytes + 1)
        if len(payload) > self._max_bytes:
            raise ValueError("source fixture exceeds size limit")
        if not payload:
            raise ValueError("source fixture is empty")
        return payload

    @staticmethod
    def _checkpoint_ordinal(source_type: str, checkpoint: str | None) -> int:
        if checkpoint is None:
            return 0
        prefix, separator, ordinal = checkpoint.rpartition(":")
        if prefix != source_type or not separator or not ordinal.isdigit():
            raise ValueError("checkpoint does not belong to connector")
        return int(ordinal)

    @staticmethod
    def _load_object(path: Path) -> JsonObject:
        value: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError("fixture catalog file must contain an object")
        return cast(JsonObject, value)

    @staticmethod
    def _object_list(row: Mapping[str, object], key: str) -> list[JsonObject]:
        value = row.get(key)
        if not isinstance(value, list):
            raise TypeError(f"fixture catalog {key} must be a list")
        result: list[JsonObject] = []
        for item in value:
            if not isinstance(item, dict):
                raise TypeError(f"fixture catalog {key} contains a non-object")
            result.append(cast(JsonObject, item))
        return result

    @staticmethod
    def _build_acl_index(
        acl: JsonObject,
    ) -> dict[str, tuple[AclRelationshipIntent, ...]]:
        resources = FixtureCatalog._object_list(acl, "resources")
        result: dict[str, tuple[AclRelationshipIntent, ...]] = {}
        for resource in resources:
            item_id = FixtureCatalog._required_string(resource, "source_item_id")
            resource_id = FixtureCatalog._required_string(resource, "resource_id")
            tenant_id = TenantId(FixtureCatalog._required_string(resource, "tenant_id"))
            tuple_values = resource.get("tuples")
            if not isinstance(tuple_values, list):
                raise TypeError("ACL tuple list is invalid")
            intents: list[AclRelationshipIntent] = []
            for tuple_value in tuple_values:
                if not isinstance(tuple_value, dict):
                    raise TypeError("ACL tuple is invalid")
                tuple_row = cast(JsonObject, tuple_value)
                intents.append(
                    AclRelationshipIntent(
                        tenant_id=tenant_id,
                        resource_id=resource_id,
                        subject=FixtureCatalog._required_string(tuple_row, "user"),
                        relation=FixtureCatalog._required_string(tuple_row, "relation"),
                    )
                )
            if item_id in result:
                raise ValueError("duplicate ACL fixture item")
            result[item_id] = tuple(intents)
        return result

    @staticmethod
    def _required_string(row: Mapping[str, object], key: str) -> str:
        value = row.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"fixture field {key} must be a non-empty string")
        return value

    @staticmethod
    def _optional_string(row: Mapping[str, object], key: str) -> str | None:
        value = row.get(key)
        if value is not None and not isinstance(value, str):
            raise TypeError(f"fixture field {key} must be a string or null")
        return value

    @staticmethod
    def _string_list(row: Mapping[str, object], key: str) -> list[str]:
        value = row.get(key)
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            raise TypeError(f"fixture field {key} must be a list of strings")
        return cast(list[str], value)

    @staticmethod
    def _required_bool(row: Mapping[str, object], key: str) -> bool:
        value = row.get(key)
        if not isinstance(value, bool):
            raise TypeError(f"fixture field {key} must be boolean")
        return value

    @staticmethod
    def _required_int(row: Mapping[str, object], key: str) -> int:
        value = row.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"fixture field {key} must be an integer")
        return value

    @staticmethod
    def _timestamp(row: Mapping[str, object], key: str) -> datetime:
        value = FixtureCatalog._required_string(row, key)
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise ValueError(f"fixture timestamp {key} must be UTC")
        return parsed.astimezone(UTC)

    @staticmethod
    def _find_duplicate_source_ids(
        items: Sequence[JsonObject],
    ) -> set[tuple[str, str, str]]:
        seen: set[tuple[str, str, str]] = set()
        duplicates: set[tuple[str, str, str]] = set()
        for item in items:
            try:
                key = (
                    FixtureCatalog._required_string(item, "tenant_id"),
                    FixtureCatalog._required_string(item, "source_type"),
                    FixtureCatalog._required_string(item, "source_external_id"),
                )
            except (TypeError, ValueError):
                continue
            if key in seen:
                duplicates.add(key)
            seen.add(key)
        return duplicates


class _FixtureConnector:
    """Common connector shell with source type fixed by the concrete adapter."""

    source_type: str

    def __init__(self, root: Path, *, max_bytes: int = 1_048_576) -> None:
        self._catalog = FixtureCatalog(root, max_bytes=max_bytes)

    def iter_changes(self, checkpoint: str | None) -> Iterable[ConnectorResult]:
        return self._catalog.changes(self.source_type, checkpoint)


class FilesystemFixtureConnector(_FixtureConnector):
    """Read document-like Markdown fixtures from the bounded fixture root."""

    source_type = "document"


class SupportTicketFixtureConnector(_FixtureConnector):
    """Read support-ticket JSON fixtures from the bounded fixture root."""

    source_type = "support_ticket"


class SlackFixtureConnector(_FixtureConnector):
    """Read Slack-style channel/thread JSON fixtures from the bounded root."""

    source_type = "slack_thread"


class CallTranscriptFixtureConnector(_FixtureConnector):
    """Read call transcript JSON fixtures from the bounded fixture root."""

    source_type = "call_transcript"
