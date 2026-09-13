"""Framework-independent contracts for source changes and raw snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import NewType

from knowledge_system.domain.persistence import DocumentId, DocumentMetadata, TenantId

RawObjectKey = NewType("RawObjectKey", str)


@dataclass(frozen=True, slots=True)
class AclRelationshipIntent:
    """A trusted source ACL mapped to an OpenFGA write intent."""

    tenant_id: TenantId
    resource_id: str
    subject: str
    relation: str

    def __post_init__(self) -> None:
        for name in ("resource_id", "subject", "relation"):
            if not getattr(self, name).strip():
                raise ValueError(f"ACL intent {name} must not be empty")
        if not str(self.tenant_id).strip():
            raise ValueError("ACL intent tenant must not be empty")


@dataclass(frozen=True, slots=True)
class RawAttachment:
    """An attachment reference; content is present only when safely available."""

    name: str
    content: bytes | None = None
    media_type: str | None = None
    external_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("attachment name must not be empty")
        if self.content is None and not self.external_ref:
            raise ValueError("attachment requires content or an external reference")


@dataclass(frozen=True, slots=True)
class SourceEnvelope:
    """One source revision emitted by a connector before parsing or indexing."""

    document_id: DocumentId
    metadata: DocumentMetadata
    external_cursor: str
    raw_content: bytes | None
    acl_relationships: tuple[AclRelationshipIntent, ...]
    is_deleted: bool
    content_type: str
    attachments: tuple[RawAttachment, ...] = ()
    source_path: str | None = None
    supersedes_document_id: DocumentId | None = None

    def __post_init__(self) -> None:
        if (
            not str(self.document_id).strip()
            or not self.external_cursor.strip()
            or not self.content_type.strip()
        ):
            raise ValueError("source envelope identity and cursor are required")
        if any(
            intent.tenant_id != self.metadata.tenant_id
            for intent in self.acl_relationships
        ):
            raise ValueError("source ACL tenant must match source metadata tenant")


@dataclass(frozen=True, slots=True)
class ConnectorFailure:
    """A per-item connector failure that must not abort unrelated source items."""

    document_id: str
    external_cursor: str
    error_code: str
    permanent: bool

    def __post_init__(self) -> None:
        for name in ("document_id", "external_cursor", "error_code"):
            if not getattr(self, name).strip():
                raise ValueError(f"connector failure {name} must not be empty")


@dataclass(frozen=True, slots=True)
class RawSnapshot:
    """Primary source bytes and provenance sent to the raw object-store port."""

    object_key: RawObjectKey
    payload: bytes
    content_type: str
    metadata: Mapping[str, str]

    def __post_init__(self) -> None:
        if not str(self.object_key).strip() or not self.content_type.strip():
            raise ValueError("raw snapshot key and content type are required")
        if not self.payload:
            raise ValueError("raw snapshot payload must not be empty")
        if any(
            not key.strip() or not value.strip() for key, value in self.metadata.items()
        ):
            raise ValueError("raw snapshot provenance metadata must be non-empty")


@dataclass(frozen=True, slots=True)
class RawObjectRef:
    """Immutable reference returned after a raw object is safely stored."""

    object_uri: str
    content_hash: str
    size_bytes: int

    def __post_init__(self) -> None:
        if (
            not self.object_uri.strip()
            or not self.content_hash.strip()
            or self.size_bytes <= 0
        ):
            raise ValueError("raw object reference is invalid")


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Minimized, non-content result of one ingestion run."""

    job_id: str
    trace_id: str
    processed_count: int
    unchanged_count: int
    failed_count: int
    deleted_count: int
    last_cursor: str | None
    status: str

    def __post_init__(self) -> None:
        if (
            min(
                self.processed_count,
                self.unchanged_count,
                self.failed_count,
                self.deleted_count,
            )
            < 0
        ):
            raise ValueError("ingestion result counts cannot be negative")
        if self.status not in {"SUCCEEDED", "FAILED"}:
            raise ValueError("ingestion result status is invalid")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded retry policy for transient connector/storage operations."""

    max_attempts: int = 3
    base_delay_seconds: float = 0.05
    max_delay_seconds: float = 1.0

    def __post_init__(self) -> None:
        if (
            self.max_attempts < 1
            or self.base_delay_seconds < 0
            or self.max_delay_seconds < 0
        ):
            raise ValueError("retry policy values are invalid")
        if self.base_delay_seconds > self.max_delay_seconds:
            raise ValueError("retry base delay cannot exceed its maximum")
