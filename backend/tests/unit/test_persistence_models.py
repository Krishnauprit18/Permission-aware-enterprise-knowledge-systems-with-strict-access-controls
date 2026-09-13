"""Unit tests for canonical persistence identities and security-bearing metadata."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from knowledge_system.domain.persistence import (
    Account,
    AccountId,
    ChunkId,
    ChunkMetadata,
    Classification,
    DeletionTombstone,
    DeletionTombstoneId,
    DocumentId,
    DocumentMetadata,
    DocumentVersion,
    DocumentVersionId,
    EvaluationCase,
    EvaluationCaseId,
    EvaluationDataset,
    EvaluationDatasetId,
    EvaluationRun,
    EvaluationRunId,
    EvaluationRunStatus,
    IngestionCheckpoint,
    IngestionJob,
    IngestionJobId,
    IngestionJobStatus,
    LifecycleStatus,
    PrincipalReference,
    QueryTraceId,
    QueryTraceMetadata,
    SourceConnection,
    SourceConnectionId,
    SourceItem,
    Tenant,
    TenantId,
    TraceOutcome,
    stable_chunk_id,
)


def metadata(
    *,
    classification: Classification = Classification.INTERNAL,
    external_shareable: bool = False,
) -> DocumentMetadata:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return DocumentMetadata(
        source_type="document",
        source_external_id="doc-1",
        source_url="https://source.invalid/doc-1",
        tenant_id=TenantId("northstar"),
        account_ids=(),
        department="product",
        created_at=timestamp,
        updated_at=timestamp,
        author="synthetic.author",
        classification=classification,
        external_shareable=external_shareable,
        authority_level=3,
        acl_relationship_refs=("resource:doc-1#viewer",),
        version=1,
        content_hash="sha256:document-1",
        language="en",
    )


@pytest.mark.unit
def test_chunk_identity_is_deterministic_and_version_sensitive() -> None:
    first = stable_chunk_id(DocumentId("doc-1"), 1, 0, "sha256:chunk")
    second = stable_chunk_id(DocumentId("doc-1"), 1, 0, "sha256:chunk")
    changed_version = stable_chunk_id(DocumentId("doc-1"), 2, 0, "sha256:chunk")

    assert first == second
    assert first != changed_version
    assert str(first).startswith("chunk_")


@pytest.mark.unit
def test_timestamps_must_be_aware_utc() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=1)))
    with pytest.raises(ValueError, match="aware UTC"):
        DocumentMetadata(
            source_type="document",
            source_external_id="doc-1",
            source_url=None,
            tenant_id=TenantId("northstar"),
            account_ids=(),
            department=None,
            created_at=timestamp,
            updated_at=timestamp,
            author=None,
            classification=Classification.INTERNAL,
            external_shareable=False,
            authority_level=1,
            acl_relationship_refs=(),
            version=1,
            content_hash="sha256:document-1",
            language="en",
        )


@pytest.mark.unit
@pytest.mark.security
def test_external_share_requires_shareable_classification() -> None:
    with pytest.raises(ValueError, match="shareable"):
        metadata(external_shareable=True)

    assert metadata(
        classification=Classification.CUSTOMER_SHAREABLE,
        external_shareable=True,
    ).external_shareable


@pytest.mark.unit
def test_deleted_source_item_requires_deletion_timestamp() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="deleted_at"):
        SourceItem(
            document_id=DocumentId("doc-1"),
            connection_id=SourceConnectionId("conn-1"),
            metadata=metadata(),
            status=LifecycleStatus.DELETED,
        )
    with pytest.raises(ValueError, match="active source items"):
        replace(
            SourceItem(DocumentId("doc-1"), SourceConnectionId("conn-1"), metadata()),
            deleted_at=timestamp,
        )
    with pytest.raises(ValueError, match="supersede itself"):
        replace(
            SourceItem(DocumentId("doc-1"), SourceConnectionId("conn-1"), metadata()),
            supersedes_document_id=DocumentId("doc-1"),
        )


@pytest.mark.unit
def test_all_canonical_entities_accept_valid_utc_values() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    tenant = Tenant(TenantId("northstar"), "Northstar", timestamp, timestamp)
    principal = PrincipalReference(
        "alice-subject", tenant.tenant_id, timestamp, timestamp
    )
    account = Account(
        AccountId("account-acme"),
        tenant.tenant_id,
        "acme",
        "Acme Retail",
        timestamp,
        timestamp,
    )
    connection = SourceConnection(
        SourceConnectionId("conn-1"),
        tenant.tenant_id,
        "document",
        "docs-1",
        None,
        "secret-ref://local/docs",
        timestamp,
        timestamp,
        retention_days=30,
    )
    document_metadata = DocumentMetadata(
        "document",
        "doc-1",
        None,
        tenant.tenant_id,
        (account.account_id,),
        "product",
        timestamp,
        timestamp,
        "alice-subject",
        Classification.CUSTOMER_SHAREABLE,
        True,
        4,
        ("resource:doc-1#viewer",),
        1,
        "sha256:doc-1",
        "en",
    )
    item = SourceItem(
        DocumentId("doc-1"),
        connection.connection_id,
        document_metadata,
        supersedes_document_id=DocumentId("doc-0"),
        lineage={"source": "docs"},
    )
    version = DocumentVersion(
        DocumentVersionId("doc-1-v1"),
        item.document_id,
        1,
        "sha256:doc-1",
        "raw://doc-1-v1",
        timestamp,
    )
    chunk = ChunkMetadata(
        stable_chunk_id(item.document_id, 1, 0, "sha256:chunk-1"),
        item.document_id,
        version.version_id,
        tenant.tenant_id,
        0,
        "sha256:chunk-1",
        "search://chunk-1",
        "embed-v1",
        "index-v1",
        timestamp,
    )
    job = IngestionJob(
        IngestionJobId("job-1"),
        tenant.tenant_id,
        connection.connection_id,
        "sync",
        "sync:docs-1:cursor-1",
        timestamp,
        IngestionJobStatus.RUNNING,
        timestamp,
    )
    checkpoint = IngestionCheckpoint(
        "checkpoint-1",
        connection.connection_id,
        job.job_id,
        "cursor-1",
        "sha256:doc-1",
        timestamp,
    )
    tombstone = DeletionTombstone(
        DeletionTombstoneId("tombstone-1"),
        tenant.tenant_id,
        "document",
        "deleted-doc",
        "source deletion",
        timestamp,
        timestamp,
        timestamp,
        processed_at=timestamp,
    )
    trace = QueryTraceMetadata(
        QueryTraceId("trace-1"),
        tenant.tenant_id,
        principal.subject_id,
        "corr-1",
        "a" * 64,
        "b" * 64,
        "trace-v1",
        TraceOutcome.REFUSED,
        timestamp,
        timestamp,
        latency_ms=5,
    )
    dataset = EvaluationDataset(
        EvaluationDatasetId("dataset-1"), "v1", "synthetic", timestamp
    )
    case = EvaluationCase(
        EvaluationCaseId("case-1"),
        dataset.dataset_id,
        "case-1",
        "What is the policy?",
        (),
        True,
    )
    run = EvaluationRun(
        EvaluationRunId("run-1"),
        dataset.dataset_id,
        timestamp,
        {"llm": "local-v1"},
        EvaluationRunStatus.RUNNING,
        retrieval_metrics={"recall@5": 0.5},
    )

    assert tenant.status is LifecycleStatus.ACTIVE
    assert principal.subject_id == "alice-subject"
    assert account.external_id == "acme"
    assert connection.retention_days == 30
    assert item.supersedes_document_id == DocumentId("doc-0")
    assert version.raw_object_ref == "raw://doc-1-v1"
    assert chunk.embedding_model_version == "embed-v1"
    assert job.started_at == timestamp
    assert checkpoint.external_cursor == "cursor-1"
    assert tombstone.processed_at == timestamp
    assert trace.latency_ms == 5
    assert case.expected_refusal
    assert run.status is EvaluationRunStatus.RUNNING


@pytest.mark.unit
def test_invalid_canonical_fields_are_rejected() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="invalid chunk"):
        stable_chunk_id(DocumentId("doc-1"), 0, 0, "hash")
    with pytest.raises(ValueError, match="invalid chunk"):
        stable_chunk_id(DocumentId("doc-1"), 1, -1, "hash")
    with pytest.raises(ValueError, match="invalid chunk"):
        stable_chunk_id(DocumentId("doc-1"), 1, 0, " ")

    with pytest.raises(ValueError, match="tenant name"):
        replace(Tenant(TenantId("t"), "Tenant", timestamp, timestamp), name=" ")
    with pytest.raises(ValueError, match="subject_id"):
        replace(
            PrincipalReference("subject", TenantId("t"), timestamp, timestamp),
            subject_id=" ",
        )
    with pytest.raises(ValueError, match="account identifiers"):
        replace(
            Account(
                AccountId("a"),
                TenantId("t"),
                "external",
                "Account",
                timestamp,
                timestamp,
            ),
            external_id=" ",
        )
    with pytest.raises(ValueError, match="account identifiers"):
        replace(
            Account(
                AccountId("a"),
                TenantId("t"),
                "external",
                "Account",
                timestamp,
                timestamp,
            ),
            name=" ",
        )
    with pytest.raises(ValueError, match="source connection identity"):
        replace(
            SourceConnection(
                SourceConnectionId("c"),
                TenantId("t"),
                "document",
                "external",
                None,
                None,
                timestamp,
                timestamp,
            ),
            source_type=" ",
        )
    with pytest.raises(ValueError, match="source connection identity"):
        replace(
            SourceConnection(
                SourceConnectionId("c"),
                TenantId("t"),
                "document",
                "external",
                None,
                None,
                timestamp,
                timestamp,
            ),
            external_id=" ",
        )
    with pytest.raises(ValueError, match="retention_days"):
        replace(
            SourceConnection(
                SourceConnectionId("c"),
                TenantId("t"),
                "document",
                "external",
                None,
                None,
                timestamp,
                timestamp,
            ),
            retention_days=0,
        )

    with pytest.raises(ValueError, match="source metadata identity"):
        replace(metadata(), source_type=" ")
    with pytest.raises(ValueError, match="source metadata identity"):
        replace(metadata(), source_external_id=" ")
    with pytest.raises(ValueError, match="version must"):
        replace(metadata(), version=0)
    with pytest.raises(ValueError, match="version must"):
        replace(metadata(), authority_level=-1)
    with pytest.raises(ValueError, match="content_hash"):
        replace(metadata(), content_hash=" ")
    with pytest.raises(ValueError, match="content_hash"):
        replace(metadata(), language=" ")

    deleted_item = SourceItem(
        DocumentId("doc-1"),
        SourceConnectionId("conn-1"),
        metadata(),
        LifecycleStatus.DELETED,
        timestamp,
        timestamp,
    )
    assert deleted_item.retention_until == timestamp
    with pytest.raises(ValueError, match="document version"):
        DocumentVersion(
            DocumentVersionId("v"), DocumentId("d"), 0, "hash", "raw", timestamp
        )
    with pytest.raises(ValueError, match="document version"):
        DocumentVersion(
            DocumentVersionId("v"), DocumentId("d"), 1, " ", "raw", timestamp
        )
    with pytest.raises(ValueError, match="document version"):
        DocumentVersion(
            DocumentVersionId("v"), DocumentId("d"), 1, "hash", " ", timestamp
        )
    valid_version = DocumentVersion(
        DocumentVersionId("v"), DocumentId("d"), 1, "hash", "raw", timestamp
    )
    with pytest.raises(ValueError, match="supersede itself"):
        replace(valid_version, supersedes_version_id=DocumentVersionId("v"))
    valid_chunk = ChunkMetadata(
        ChunkId("chunk-1"),
        DocumentId("d"),
        DocumentVersionId("v"),
        TenantId("t"),
        0,
        "hash",
        "search",
        None,
        None,
        timestamp,
    )
    with pytest.raises(ValueError, match="chunk metadata"):
        replace(valid_chunk, ordinal=-1)
    with pytest.raises(ValueError, match="chunk metadata"):
        replace(valid_chunk, content_hash=" ")
    with pytest.raises(ValueError, match="chunk metadata"):
        replace(valid_chunk, search_document_ref=" ")
    with pytest.raises(ValueError, match="deleted chunks"):
        replace(valid_chunk, status=LifecycleStatus.DELETED)
    with pytest.raises(ValueError, match="active chunks"):
        replace(valid_chunk, deleted_at=timestamp)
    assert (
        replace(
            valid_chunk, status=LifecycleStatus.DELETED, deleted_at=timestamp
        ).deleted_at
        == timestamp
    )

    valid_job = IngestionJob(
        IngestionJobId("job"),
        TenantId("t"),
        None,
        "sync",
        "key",
        timestamp,
    )
    with pytest.raises(ValueError, match="ingestion job"):
        replace(valid_job, kind=" ")
    with pytest.raises(ValueError, match="ingestion job"):
        replace(valid_job, idempotency_key=" ")
    assert replace(valid_job, finished_at=timestamp).finished_at == timestamp
    with pytest.raises(ValueError, match="external_cursor"):
        IngestionCheckpoint(
            "cp", SourceConnectionId("c"), IngestionJobId("j"), " ", None, timestamp
        )
    with pytest.raises(ValueError, match="tombstone source"):
        DeletionTombstone(
            DeletionTombstoneId("t"),
            TenantId("t"),
            " ",
            "id",
            "reason",
            timestamp,
            timestamp,
            timestamp,
        )
    with pytest.raises(ValueError, match="tombstone source"):
        DeletionTombstone(
            DeletionTombstoneId("t"),
            TenantId("t"),
            "document",
            " ",
            "reason",
            timestamp,
            timestamp,
            timestamp,
        )

    valid_trace = QueryTraceMetadata(
        QueryTraceId("trace"),
        TenantId("t"),
        "subject",
        "corr",
        "q",
        "a",
        "v1",
        TraceOutcome.ANSWERED,
        timestamp,
        timestamp,
    )
    with pytest.raises(ValueError, match="latency"):
        replace(valid_trace, latency_ms=-1)
    with pytest.raises(ValueError, match="hashes"):
        replace(valid_trace, query_hash=" ")
    with pytest.raises(ValueError, match="hashes"):
        replace(valid_trace, authorization_fingerprint=" ")
    with pytest.raises(ValueError, match="evaluation dataset"):
        EvaluationDataset(EvaluationDatasetId("d"), " ", "description", timestamp)
    with pytest.raises(ValueError, match="evaluation dataset"):
        EvaluationDataset(EvaluationDatasetId("d"), "v1", " ", timestamp)
    with pytest.raises(ValueError, match="evaluation case"):
        EvaluationCase(
            EvaluationCaseId("c"), EvaluationDatasetId("d"), " ", "question", (), False
        )
    with pytest.raises(ValueError, match="evaluation case"):
        EvaluationCase(
            EvaluationCaseId("c"), EvaluationDatasetId("d"), "key", " ", (), False
        )
