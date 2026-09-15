"""Framework-independent canonical persistence objects and identity helpers."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from typing import NewType

TenantId = NewType("TenantId", str)
AccountId = NewType("AccountId", str)
SourceConnectionId = NewType("SourceConnectionId", str)
DocumentId = NewType("DocumentId", str)
DocumentVersionId = NewType("DocumentVersionId", str)
ChunkId = NewType("ChunkId", str)
IngestionJobId = NewType("IngestionJobId", str)
DeletionTombstoneId = NewType("DeletionTombstoneId", str)
QueryTraceId = NewType("QueryTraceId", str)
EvaluationDatasetId = NewType("EvaluationDatasetId", str)
EvaluationCaseId = NewType("EvaluationCaseId", str)
EvaluationRunId = NewType("EvaluationRunId", str)


class Classification(StrEnum):
    """Trusted source classification values."""

    PUBLIC = "PUBLIC"
    CUSTOMER_SHAREABLE = "CUSTOMER_SHAREABLE"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class LifecycleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DELETED = "DELETED"


class SourceConnectionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"


class IngestionJobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TraceOutcome(StrEnum):
    ANSWERED = "ANSWERED"
    REFUSED = "REFUSED"
    FAILED = "FAILED"


class EvaluationRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def ensure_utc(value: datetime, field_name: str) -> datetime:
    """Require an aware UTC timestamp and normalize equivalent UTC values."""

    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be an aware UTC timestamp")
    return value.astimezone(UTC)


def stable_chunk_id(
    document_id: DocumentId,
    document_version: int,
    ordinal: int,
    content_hash: str,
) -> ChunkId:
    """Build a deterministic citation identity from immutable chunk inputs."""

    if document_version < 1 or ordinal < 0 or not content_hash.strip():
        raise ValueError("invalid chunk identity inputs")
    material = f"{document_id}|v{document_version}|{ordinal}|{content_hash}"
    return ChunkId(f"chunk_{sha256(material.encode('utf-8')).hexdigest()}")


@dataclass(frozen=True, slots=True)
class Tenant:
    tenant_id: TenantId
    name: str
    created_at: datetime
    updated_at: datetime
    status: LifecycleStatus = LifecycleStatus.ACTIVE

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "created_at", ensure_utc(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", ensure_utc(self.updated_at, "updated_at")
        )
        if not self.name.strip():
            raise ValueError("tenant name must not be empty")


@dataclass(frozen=True, slots=True)
class PrincipalReference:
    """Non-secret reference to an identity managed by Keycloak."""

    subject_id: str
    tenant_id: TenantId
    created_at: datetime
    updated_at: datetime
    status: LifecycleStatus = LifecycleStatus.ACTIVE
    display_name: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "created_at", ensure_utc(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", ensure_utc(self.updated_at, "updated_at")
        )
        if not self.subject_id.strip():
            raise ValueError("subject_id must not be empty")


@dataclass(frozen=True, slots=True)
class Account:
    account_id: AccountId
    tenant_id: TenantId
    external_id: str
    name: str
    created_at: datetime
    updated_at: datetime
    status: LifecycleStatus = LifecycleStatus.ACTIVE

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "created_at", ensure_utc(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", ensure_utc(self.updated_at, "updated_at")
        )
        if not self.external_id.strip() or not self.name.strip():
            raise ValueError("account identifiers and name must not be empty")


@dataclass(frozen=True, slots=True)
class SourceConnection:
    connection_id: SourceConnectionId
    tenant_id: TenantId
    source_type: str
    external_id: str
    base_url: str | None
    credentials_ref: str | None
    created_at: datetime
    updated_at: datetime
    status: SourceConnectionStatus = SourceConnectionStatus.ACTIVE
    retention_days: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "created_at", ensure_utc(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", ensure_utc(self.updated_at, "updated_at")
        )
        if not self.source_type.strip() or not self.external_id.strip():
            raise ValueError("source connection identity must not be empty")
        if self.retention_days is not None and self.retention_days < 1:
            raise ValueError("retention_days must be positive")


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    """Canonical metadata; it contains references, never document text."""

    source_type: str
    source_external_id: str
    source_url: str | None
    tenant_id: TenantId
    account_ids: tuple[AccountId, ...]
    department: str | None
    created_at: datetime
    updated_at: datetime
    author: str | None
    classification: Classification
    external_shareable: bool
    authority_level: int
    acl_relationship_refs: tuple[str, ...]
    version: int
    content_hash: str
    language: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "created_at", ensure_utc(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", ensure_utc(self.updated_at, "updated_at")
        )
        if not self.source_type.strip() or not self.source_external_id.strip():
            raise ValueError("source metadata identity must not be empty")
        if self.version < 1 or self.authority_level < 0:
            raise ValueError("version must be positive and authority non-negative")
        if not self.content_hash.strip() or not self.language.strip():
            raise ValueError("content_hash and language must not be empty")
        if self.external_shareable and self.classification not in {
            Classification.PUBLIC,
            Classification.CUSTOMER_SHAREABLE,
        }:
            raise ValueError("only public or customer-shareable content may be shared")


@dataclass(frozen=True, slots=True)
class SourceItem:
    document_id: DocumentId
    connection_id: SourceConnectionId
    metadata: DocumentMetadata
    status: LifecycleStatus = LifecycleStatus.ACTIVE
    deleted_at: datetime | None = None
    retention_until: datetime | None = None
    supersedes_document_id: DocumentId | None = None
    lineage: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.metadata.tenant_id is None:
            raise ValueError("source item requires a tenant")
        if self.deleted_at is not None:
            object.__setattr__(
                self, "deleted_at", ensure_utc(self.deleted_at, "deleted_at")
            )
        if self.retention_until is not None:
            object.__setattr__(
                self,
                "retention_until",
                ensure_utc(self.retention_until, "retention_until"),
            )
        if self.status is LifecycleStatus.DELETED and self.deleted_at is None:
            raise ValueError("deleted source items require deleted_at")
        if self.status is LifecycleStatus.ACTIVE and self.deleted_at is not None:
            raise ValueError("active source items cannot have deleted_at")
        if self.supersedes_document_id == self.document_id:
            raise ValueError("source item cannot supersede itself")


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    version_id: DocumentVersionId
    document_id: DocumentId
    version: int
    content_hash: str
    raw_object_ref: str
    created_at: datetime
    supersedes_version_id: DocumentVersionId | None = None
    status: LifecycleStatus = LifecycleStatus.ACTIVE

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "created_at", ensure_utc(self.created_at, "created_at")
        )
        if (
            self.version < 1
            or not self.content_hash.strip()
            or not self.raw_object_ref.strip()
        ):
            raise ValueError(
                "document version requires positive version and references"
            )
        if self.supersedes_version_id == self.version_id:
            raise ValueError("document version cannot supersede itself")


@dataclass(frozen=True, slots=True)
class ChunkMetadata:
    chunk_id: ChunkId
    document_id: DocumentId
    version_id: DocumentVersionId
    tenant_id: TenantId
    ordinal: int
    content_hash: str
    search_document_ref: str
    embedding_model_version: str | None
    index_schema_version: str | None
    created_at: datetime
    status: LifecycleStatus = LifecycleStatus.ACTIVE
    deleted_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "created_at", ensure_utc(self.created_at, "created_at")
        )
        if (
            self.ordinal < 0
            or not self.content_hash.strip()
            or not self.search_document_ref.strip()
        ):
            raise ValueError("chunk metadata identity and references are required")
        if self.deleted_at is not None:
            object.__setattr__(
                self, "deleted_at", ensure_utc(self.deleted_at, "deleted_at")
            )
        if self.status is LifecycleStatus.DELETED and self.deleted_at is None:
            raise ValueError("deleted chunks require deleted_at")
        if self.status is LifecycleStatus.ACTIVE and self.deleted_at is not None:
            raise ValueError("active chunks cannot have deleted_at")


@dataclass(frozen=True, slots=True)
class IngestionJob:
    job_id: IngestionJobId
    tenant_id: TenantId
    connection_id: SourceConnectionId | None
    kind: str
    idempotency_key: str
    created_at: datetime
    status: IngestionJobStatus = IngestionJobStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "created_at", ensure_utc(self.created_at, "created_at")
        )
        for name in ("started_at", "finished_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, ensure_utc(value, name))
        if not self.kind.strip() or not self.idempotency_key.strip():
            raise ValueError("ingestion job kind and idempotency key are required")


@dataclass(frozen=True, slots=True)
class IngestionCheckpoint:
    checkpoint_id: str
    connection_id: SourceConnectionId
    job_id: IngestionJobId
    external_cursor: str
    content_hash: str | None
    committed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "committed_at", ensure_utc(self.committed_at, "committed_at")
        )
        if not self.external_cursor.strip():
            raise ValueError("external_cursor must not be empty")


@dataclass(frozen=True, slots=True)
class DeletionTombstone:
    tombstone_id: DeletionTombstoneId
    tenant_id: TenantId
    source_type: str
    source_external_id: str
    reason: str
    observed_at: datetime
    effective_at: datetime
    retention_until: datetime
    source_item_id: DocumentId | None = None
    processed_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("observed_at", "effective_at", "retention_until", "processed_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, ensure_utc(value, name))
        if not self.source_type.strip() or not self.source_external_id.strip():
            raise ValueError("tombstone source identity is required")


@dataclass(frozen=True, slots=True)
class QueryTraceMetadata:
    trace_id: QueryTraceId
    tenant_id: TenantId
    principal_subject_id: str
    correlation_id: str
    query_hash: str
    authorization_fingerprint: str
    schema_version: str
    outcome: TraceOutcome
    created_at: datetime
    retention_until: datetime
    evidence_ids: tuple[str, ...] = ()
    latency_ms: int | None = None
    audit_metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "created_at", ensure_utc(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "retention_until", ensure_utc(self.retention_until, "retention_until")
        )
        if self.latency_ms is not None and self.latency_ms < 0:
            raise ValueError("latency_ms must not be negative")
        if not self.query_hash.strip() or not self.authorization_fingerprint.strip():
            raise ValueError("query and authorization hashes are required")


@dataclass(frozen=True, slots=True)
class EvaluationDataset:
    dataset_id: EvaluationDatasetId
    version: str
    description: str
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "created_at", ensure_utc(self.created_at, "created_at")
        )
        if not self.version.strip() or not self.description.strip():
            raise ValueError("evaluation dataset version and description are required")


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: EvaluationCaseId
    dataset_id: EvaluationDatasetId
    case_key: str
    question: str
    expected_evidence_ids: tuple[str, ...]
    expected_refusal: bool

    def __post_init__(self) -> None:
        if not self.case_key.strip() or not self.question.strip():
            raise ValueError("evaluation case key and question are required")


@dataclass(frozen=True, slots=True)
class EvaluationRun:
    run_id: EvaluationRunId
    dataset_id: EvaluationDatasetId
    started_at: datetime
    model_versions: Mapping[str, str]
    status: EvaluationRunStatus
    completed_at: datetime | None = None
    retrieval_metrics: Mapping[str, float] = field(default_factory=dict)
    generation_metrics: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "started_at", ensure_utc(self.started_at, "started_at")
        )
        if self.completed_at is not None:
            object.__setattr__(
                self, "completed_at", ensure_utc(self.completed_at, "completed_at")
            )
