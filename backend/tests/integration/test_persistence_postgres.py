"""PostgreSQL migration and repository integration tests."""

import os
from collections.abc import Callable, Generator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import psycopg
import pytest
from psycopg import Connection
from psycopg.sql import SQL, Identifier

from knowledge_system.adapters.persistence.postgres import (
    PostgresUnitOfWork,
)
from knowledge_system.application.ports.persistence import (
    CanonicalRepository,
    PersistenceError,
)
from knowledge_system.domain.persistence import (
    Account,
    AccountId,
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

ROOT = Path(__file__).parents[3]
MIGRATION = ROOT / "backend" / "migrations" / "0001_initial.sql"
DatabaseFactory = Callable[[], Connection[dict[str, object]]]
IsolatedDatabase = tuple[DatabaseFactory, str]


@dataclass(frozen=True, slots=True)
class SeedObjects:
    tenant: Tenant
    principal: PrincipalReference
    account: Account
    connection: SourceConnection
    item: SourceItem
    version: DocumentVersion
    chunk: ChunkMetadata
    job: IngestionJob
    checkpoint: IngestionCheckpoint
    tombstone: DeletionTombstone
    trace: QueryTraceMetadata
    dataset: EvaluationDataset
    case: EvaluationCase
    run: EvaluationRun


def _database_url() -> str | None:
    configured = os.environ.get("DATABASE_URL")
    if configured:
        return configured
    env_file = ROOT / ".env.local"
    if not env_file.exists():
        return None
    values: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    user = values.get("POSTGRES_USER")
    password = values.get("POSTGRES_PASSWORD")
    database = values.get("POSTGRES_DB")
    if not user or not password or not database:
        return None
    return (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{os.environ.get('P07_DATABASE_HOST', 'localhost')}:5432/{quote(database, safe='')}"
    )


@pytest.fixture
def isolated_database() -> Generator[IsolatedDatabase, None, None]:
    url = _database_url()
    if url is None:
        pytest.skip(
            "DATABASE_URL or .env.local is required for PostgreSQL integration tests"
        )
    try:
        connection = psycopg.connect(url)
    except psycopg.Error as exc:
        pytest.skip(
            f"PostgreSQL is unavailable for integration tests: {type(exc).__name__}"
        )
    schema = f"p07_test_{uuid4().hex}"
    try:
        with connection.transaction():
            connection.execute(SQL("CREATE SCHEMA {} ").format(Identifier(schema)))
            connection.execute(SQL("SET search_path TO {} ").format(Identifier(schema)))
            connection.execute(MIGRATION.read_text(encoding="utf-8"))
        yield connection_factory(url, schema), schema
    finally:
        connection.execute("SET search_path TO public")
        connection.execute(
            SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(Identifier(schema))
        )
        connection.commit()
        connection.close()


def connection_factory(url: str, schema: str) -> DatabaseFactory:
    def connect() -> Connection[dict[str, object]]:
        connection = psycopg.connect(url, row_factory=psycopg.rows.dict_row)
        connection.execute(SQL("SET search_path TO {} ").format(Identifier(schema)))
        return connection

    return connect


def seed_objects() -> SeedObjects:
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
        SourceConnectionId("conn-docs"),
        tenant.tenant_id,
        "document",
        "docs-main",
        "https://source.invalid",
        "secret-ref://local/document",
        timestamp,
        timestamp,
    )
    metadata = DocumentMetadata(
        source_type="document",
        source_external_id="doc-1",
        source_url="https://source.invalid/doc-1",
        tenant_id=tenant.tenant_id,
        account_ids=(account.account_id,),
        department="sales-customer-success",
        created_at=timestamp,
        updated_at=timestamp,
        author="alice-subject",
        classification=Classification.INTERNAL,
        external_shareable=False,
        authority_level=3,
        acl_relationship_refs=("resource:doc-1#viewer",),
        version=1,
        content_hash="sha256:doc-1",
        language="en",
    )
    item = SourceItem(DocumentId("doc-1"), connection.connection_id, metadata)
    version = DocumentVersion(
        DocumentVersionId("doc-1-v1"),
        item.document_id,
        1,
        metadata.content_hash,
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
        "sync:docs-main:cursor-1",
        timestamp,
    )
    checkpoint = IngestionCheckpoint(
        "checkpoint-1",
        connection.connection_id,
        job.job_id,
        "cursor-1",
        metadata.content_hash,
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
        timestamp + timedelta(days=30),
    )
    trace = QueryTraceMetadata(
        QueryTraceId("trace-1"),
        tenant.tenant_id,
        principal.subject_id,
        "corr-1",
        "a" * 64,
        "b" * 64,
        "trace-v1",
        TraceOutcome.ANSWERED,
        timestamp,
        timestamp + timedelta(days=30),
        (str(chunk.chunk_id),),
        12,
    )
    dataset = EvaluationDataset(
        EvaluationDatasetId("dataset-1"), "v1", "synthetic dataset", timestamp
    )
    case = EvaluationCase(
        EvaluationCaseId("case-1"),
        dataset.dataset_id,
        "lookup-1",
        "Where is the account guide?",
        (str(chunk.chunk_id),),
        False,
    )
    run = EvaluationRun(
        EvaluationRunId("run-1"),
        dataset.dataset_id,
        timestamp,
        {"llm": "local-v1"},
        EvaluationRunStatus.SUCCEEDED,
        timestamp,
        {"recall@5": 1.0},
        {"grounded": 1.0},
    )
    return SeedObjects(
        tenant,
        principal,
        account,
        connection,
        item,
        version,
        chunk,
        job,
        checkpoint,
        tombstone,
        trace,
        dataset,
        case,
        run,
    )


def save_all(repository: CanonicalRepository, objects: SeedObjects) -> None:
    repository.save_tenant(objects.tenant)
    repository.save_principal_reference(objects.principal)
    repository.save_account(objects.account)
    repository.save_source_connection(objects.connection)
    repository.save_source_item(objects.item)
    repository.append_document_version(objects.version)
    repository.save_chunk_metadata(objects.chunk)
    repository.save_ingestion_job(objects.job)
    repository.save_ingestion_checkpoint(objects.checkpoint)
    repository.save_deletion_tombstone(objects.tombstone)
    repository.save_query_trace(objects.trace)
    repository.save_evaluation_dataset(objects.dataset)
    repository.save_evaluation_case(objects.case)
    repository.save_evaluation_run(objects.run)


@pytest.mark.integration
def test_empty_database_migration_creates_required_tables(
    isolated_database: IsolatedDatabase,
) -> None:
    factory, schema = isolated_database
    with factory() as connection:
        connection.execute(SQL("SET search_path TO {} ").format(Identifier(schema)))
        tables = connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
            (schema,),
        ).fetchall()
    assert {
        "schema_migrations",
        "tenants",
        "principal_references",
        "accounts",
        "source_connections",
        "source_items",
        "document_versions",
        "chunks",
        "ingestion_jobs",
        "ingestion_checkpoints",
        "deletion_tombstones",
        "query_traces",
        "evaluation_datasets",
        "evaluation_cases",
        "evaluation_runs",
    }.issubset({_required_table_name(row) for row in tables})


@pytest.mark.integration
def test_repository_seed_is_idempotent_and_preserves_lineage(
    isolated_database: IsolatedDatabase,
) -> None:
    factory, schema = isolated_database
    objects = seed_objects()
    with PostgresUnitOfWork(factory) as repository:
        save_all(repository, objects)
    with PostgresUnitOfWork(factory) as repository:
        save_all(repository, objects)
        loaded = repository.get_source_item("doc-1")
    assert loaded is not None
    assert loaded.metadata.account_ids == (AccountId("account-acme"),)
    assert loaded.metadata.version == 1

    with factory() as connection:
        connection.execute(SQL("SET search_path TO {} ").format(Identifier(schema)))
        counts = connection.execute(
            """
            SELECT (SELECT count(*) FROM tenants) AS tenants,
                   (SELECT count(*) FROM source_items) AS source_items,
                   (SELECT count(*) FROM document_versions) AS document_versions,
                   (SELECT count(*) FROM chunks) AS chunks,
                   (SELECT count(*) FROM ingestion_jobs) AS ingestion_jobs,
                   (SELECT count(*) FROM ingestion_checkpoints) AS ingestion_checkpoints
            """
        ).fetchone()
    assert counts == {
        "tenants": 1,
        "source_items": 1,
        "document_versions": 1,
        "chunks": 1,
        "ingestion_jobs": 1,
        "ingestion_checkpoints": 1,
    }


@pytest.mark.integration
@pytest.mark.security
def test_transaction_rolls_back_and_integrity_conflicts_fail_closed(
    isolated_database: IsolatedDatabase,
) -> None:
    factory, schema = isolated_database
    objects = seed_objects()
    with (
        pytest.raises(RuntimeError, match="rollback sentinel"),
        PostgresUnitOfWork(factory) as repository,
    ):
        repository.save_tenant(objects.tenant)
        raise RuntimeError("rollback sentinel")
    with factory() as connection:
        connection.execute(SQL("SET search_path TO {} ").format(Identifier(schema)))
        assert connection.execute(
            "SELECT count(*) AS count FROM tenants"
        ).fetchone() == {"count": 0}

    with PostgresUnitOfWork(factory) as repository:
        save_all(repository, objects)
    conflicting = DocumentVersion(
        DocumentVersionId("doc-1-v1"),
        DocumentId("doc-1"),
        1,
        "sha256:different",
        "raw://different",
        datetime(2026, 1, 2, tzinfo=UTC),
    )
    with (
        pytest.raises(PersistenceError, match="identity conflict"),
        PostgresUnitOfWork(factory) as repository,
    ):
        repository.append_document_version(conflicting)


@pytest.mark.integration
@pytest.mark.security
def test_tenant_identity_and_relationship_constraints_cannot_be_rebound(
    isolated_database: IsolatedDatabase,
) -> None:
    factory, schema = isolated_database
    objects = seed_objects()
    with PostgresUnitOfWork(factory) as repository:
        save_all(repository, objects)

    other_tenant = replace(objects.tenant, tenant_id=TenantId("other"))
    rebound_account = replace(objects.account, tenant_id=other_tenant.tenant_id)
    with (
        pytest.raises(PersistenceError, match="account identity conflict"),
        PostgresUnitOfWork(factory) as repository,
    ):
        repository.save_tenant(other_tenant)
        repository.save_account(rebound_account)

    cross_tenant_item = replace(
        objects.item,
        metadata=replace(
            objects.item.metadata,
            account_ids=(AccountId("account-other"),),
        ),
    )
    with (
        pytest.raises(PersistenceError, match="canonical persistence operation failed"),
        PostgresUnitOfWork(factory) as repository,
    ):
        repository.save_source_item(cross_tenant_item)

    with factory() as connection:
        connection.execute(SQL("SET search_path TO {} ").format(Identifier(schema)))
        account = connection.execute(
            "SELECT tenant_id FROM accounts WHERE account_id = %s",
            (str(objects.account.account_id),),
        ).fetchone()
    assert account == {"tenant_id": str(objects.tenant.tenant_id)}


@pytest.mark.integration
def test_deleted_item_and_tombstone_are_durable_markers(
    isolated_database: IsolatedDatabase,
) -> None:
    factory, schema = isolated_database
    objects = seed_objects()
    item = objects.item
    timestamp = datetime(2026, 1, 2, tzinfo=UTC)
    objects = SeedObjects(
        objects.tenant,
        objects.principal,
        objects.account,
        objects.connection,
        SourceItem(
            item.document_id,
            item.connection_id,
            item.metadata,
            LifecycleStatus.DELETED,
            timestamp,
        ),
        objects.version,
        objects.chunk,
        objects.job,
        objects.checkpoint,
        objects.tombstone,
        objects.trace,
        objects.dataset,
        objects.case,
        objects.run,
    )
    with PostgresUnitOfWork(factory) as repository:
        save_all(repository, objects)
        loaded = repository.get_source_item("doc-1")
    assert loaded is not None
    assert loaded.status is LifecycleStatus.DELETED
    assert loaded.deleted_at == timestamp
    with factory() as connection:
        connection.execute(SQL("SET search_path TO {} ").format(Identifier(schema)))
        assert connection.execute(
            "SELECT count(*) AS count FROM deletion_tombstones"
        ).fetchone() == {"count": 1}


def _required_table_name(row: dict[str, object]) -> str:
    value = row.get("table_name")
    if not isinstance(value, str):
        raise TypeError("migration table name was not text")
    return value
