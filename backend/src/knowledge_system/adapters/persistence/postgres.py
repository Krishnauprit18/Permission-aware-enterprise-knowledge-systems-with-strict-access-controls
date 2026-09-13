"""PostgreSQL adapter for canonical control metadata."""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Literal, cast

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from knowledge_system.application.ports.persistence import (
    CanonicalRepository,
    PersistenceError,
    UnitOfWork,
)
from knowledge_system.domain.persistence import (
    Account,
    AccountId,
    ChunkMetadata,
    Classification,
    DeletionTombstone,
    DocumentId,
    DocumentMetadata,
    DocumentVersion,
    EvaluationCase,
    EvaluationDataset,
    EvaluationRun,
    IngestionCheckpoint,
    IngestionJob,
    LifecycleStatus,
    PrincipalReference,
    QueryTraceMetadata,
    SourceConnection,
    SourceConnectionId,
    SourceItem,
    Tenant,
)

ConnectionFactory = Callable[[], Connection[dict[str, object]]]


class PostgresUnitOfWork(UnitOfWork):
    """Own one connection and its commit/rollback boundary."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory
        self._connection: Connection[dict[str, object]] | None = None
        self.repository: CanonicalRepository

    def __enter__(self) -> CanonicalRepository:
        if self._connection is not None:
            raise PersistenceError("unit of work cannot be entered twice")
        self._connection = self._connection_factory()
        self.repository = PostgresCanonicalRepository(self._connection)
        return self.repository

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> Literal[False]:
        del exc, tb
        connection = self._connection
        if connection is None:
            return False
        try:
            if exc_type is None:
                connection.commit()
            else:
                connection.rollback()
        finally:
            connection.close()
            self._connection = None
        return False


class PostgresCanonicalRepository(CanonicalRepository):
    """Persist canonical objects without creating or altering schema at runtime."""

    def __init__(self, connection: Connection[dict[str, object]]) -> None:
        self._connection = connection

    def save_tenant(self, tenant: Tenant) -> None:
        self._execute(
            """
            INSERT INTO tenants (tenant_id, name, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id) DO UPDATE SET
                name = EXCLUDED.name, status = EXCLUDED.status,
                updated_at = EXCLUDED.updated_at
            """,
            (
                str(tenant.tenant_id),
                tenant.name,
                tenant.status.value,
                tenant.created_at,
                tenant.updated_at,
            ),
        )

    def save_principal_reference(self, principal: PrincipalReference) -> None:
        self._execute(
            """
            INSERT INTO principal_references
                (subject_id, tenant_id, display_name, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (subject_id) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                status = EXCLUDED.status, updated_at = EXCLUDED.updated_at
            """,
            (
                principal.subject_id,
                str(principal.tenant_id),
                principal.display_name,
                principal.status.value,
                principal.created_at,
                principal.updated_at,
            ),
        )
        row = self._fetchone(
            "SELECT tenant_id FROM principal_references WHERE subject_id = %s",
            (principal.subject_id,),
        )
        if row is None or _required_str(row, "tenant_id") != str(principal.tenant_id):
            raise PersistenceError("principal tenant identity conflict")

    def save_account(self, account: Account) -> None:
        self._execute(
            """
            INSERT INTO accounts
                (account_id, tenant_id, external_id, name, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (account_id) DO UPDATE SET
                name = EXCLUDED.name, status = EXCLUDED.status,
                updated_at = EXCLUDED.updated_at
            """,
            (
                str(account.account_id),
                str(account.tenant_id),
                account.external_id,
                account.name,
                account.status.value,
                account.created_at,
                account.updated_at,
            ),
        )
        row = self._fetchone(
            "SELECT tenant_id, external_id FROM accounts WHERE account_id = %s",
            (str(account.account_id),),
        )
        if row is None or (
            _required_str(row, "tenant_id") != str(account.tenant_id)
            or _required_str(row, "external_id") != account.external_id
        ):
            raise PersistenceError("account identity conflict")

    def save_source_connection(self, connection: SourceConnection) -> None:
        self._execute(
            """
            INSERT INTO source_connections
                (connection_id, tenant_id, source_type, external_id, base_url,
                 credentials_ref, status, retention_days, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (connection_id) DO UPDATE SET
                base_url = EXCLUDED.base_url,
                credentials_ref = EXCLUDED.credentials_ref, status = EXCLUDED.status,
                retention_days = EXCLUDED.retention_days, updated_at = EXCLUDED.updated_at
            """,
            (
                str(connection.connection_id),
                str(connection.tenant_id),
                connection.source_type,
                connection.external_id,
                connection.base_url,
                connection.credentials_ref,
                connection.status.value,
                connection.retention_days,
                connection.created_at,
                connection.updated_at,
            ),
        )
        row = self._fetchone(
            "SELECT tenant_id, source_type, external_id FROM source_connections "
            "WHERE connection_id = %s",
            (str(connection.connection_id),),
        )
        if row is None or (
            _required_str(row, "tenant_id") != str(connection.tenant_id)
            or _required_str(row, "source_type") != connection.source_type
            or _required_str(row, "external_id") != connection.external_id
        ):
            raise PersistenceError("source connection identity conflict")

    def save_source_item(self, item: SourceItem) -> None:
        metadata = item.metadata
        self._execute(
            """
            INSERT INTO source_items
                (document_id, connection_id, tenant_id, source_type,
                 source_external_id, source_url, department, author, classification,
                 external_shareable, authority_level, acl_relationship_refs, version,
                 content_hash, language, status, deleted_at, retention_until,
                 supersedes_document_id, lineage, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (document_id) DO UPDATE SET
                source_url = EXCLUDED.source_url, department = EXCLUDED.department,
                author = EXCLUDED.author, classification = EXCLUDED.classification,
                external_shareable = EXCLUDED.external_shareable,
                authority_level = EXCLUDED.authority_level,
                acl_relationship_refs = EXCLUDED.acl_relationship_refs,
                version = EXCLUDED.version, content_hash = EXCLUDED.content_hash,
                language = EXCLUDED.language, status = EXCLUDED.status,
                deleted_at = EXCLUDED.deleted_at, retention_until = EXCLUDED.retention_until,
                supersedes_document_id = EXCLUDED.supersedes_document_id,
                lineage = EXCLUDED.lineage, updated_at = EXCLUDED.updated_at
            """,
            (
                str(item.document_id),
                str(item.connection_id),
                str(metadata.tenant_id),
                metadata.source_type,
                metadata.source_external_id,
                metadata.source_url,
                metadata.department,
                metadata.author,
                metadata.classification.value,
                metadata.external_shareable,
                metadata.authority_level,
                Jsonb(list(metadata.acl_relationship_refs)),
                metadata.version,
                metadata.content_hash,
                metadata.language,
                item.status.value,
                item.deleted_at,
                item.retention_until,
                str(item.supersedes_document_id)
                if item.supersedes_document_id
                else None,
                Jsonb(dict(item.lineage)),
                metadata.created_at,
                metadata.updated_at,
            ),
        )
        row = self._fetchone(
            "SELECT connection_id, tenant_id, source_type, source_external_id "
            "FROM source_items WHERE document_id = %s",
            (str(item.document_id),),
        )
        if row is None or (
            _required_str(row, "connection_id") != str(item.connection_id)
            or _required_str(row, "tenant_id") != str(metadata.tenant_id)
            or _required_str(row, "source_type") != metadata.source_type
            or _required_str(row, "source_external_id") != metadata.source_external_id
        ):
            raise PersistenceError("source item identity conflict")
        self._execute(
            "DELETE FROM source_item_accounts WHERE document_id = %s",
            (str(item.document_id),),
        )
        for account_id in metadata.account_ids:
            self._execute(
                """
                INSERT INTO source_item_accounts (document_id, tenant_id, account_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (document_id, account_id) DO NOTHING
                """,
                (str(item.document_id), str(metadata.tenant_id), str(account_id)),
            )

    def append_document_version(self, version: DocumentVersion) -> None:
        self._execute(
            """
            INSERT INTO document_versions
                (version_id, document_id, tenant_id, version, content_hash,
                 raw_object_ref, status, supersedes_version_id, created_at)
            SELECT %s, document_id, tenant_id, %s, %s, %s, %s, %s, %s
            FROM source_items WHERE document_id = %s
            ON CONFLICT (version_id) DO NOTHING
            """,
            (
                str(version.version_id),
                version.version,
                version.content_hash,
                version.raw_object_ref,
                version.status.value,
                str(version.supersedes_version_id)
                if version.supersedes_version_id
                else None,
                version.created_at,
                str(version.document_id),
            ),
        )
        row = self._fetchone(
            """
            SELECT document_id, version, content_hash, raw_object_ref
            FROM document_versions WHERE version_id = %s
            """,
            (str(version.version_id),),
        )
        if row is None or (
            _required_str(row, "document_id") != str(version.document_id)
            or _required_int(row, "version") != version.version
            or _required_str(row, "content_hash") != version.content_hash
            or _required_str(row, "raw_object_ref") != version.raw_object_ref
        ):
            raise PersistenceError("document version identity conflict")

    def save_chunk_metadata(self, chunk: ChunkMetadata) -> None:
        self._execute(
            """
            INSERT INTO chunks
                (chunk_id, document_id, version_id, tenant_id, ordinal, content_hash,
                 search_document_ref, embedding_model_version, index_schema_version,
                 status, deleted_at, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (chunk_id) DO NOTHING
            """,
            (
                str(chunk.chunk_id),
                str(chunk.document_id),
                str(chunk.version_id),
                str(chunk.tenant_id),
                chunk.ordinal,
                chunk.content_hash,
                chunk.search_document_ref,
                chunk.embedding_model_version,
                chunk.index_schema_version,
                chunk.status.value,
                chunk.deleted_at,
                chunk.created_at,
            ),
        )
        row = self._fetchone(
            "SELECT document_id, version_id, ordinal, content_hash FROM chunks WHERE chunk_id = %s",
            (str(chunk.chunk_id),),
        )
        if row is None or (
            _required_str(row, "document_id") != str(chunk.document_id)
            or _required_str(row, "version_id") != str(chunk.version_id)
            or _required_int(row, "ordinal") != chunk.ordinal
            or _required_str(row, "content_hash") != chunk.content_hash
        ):
            raise PersistenceError("chunk identity conflict")

    def save_ingestion_job(self, job: IngestionJob) -> None:
        self._execute(
            """
            INSERT INTO ingestion_jobs
                (job_id, tenant_id, connection_id, kind, idempotency_key, status,
                 error_code, started_at, finished_at, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            """,
            (
                str(job.job_id),
                str(job.tenant_id),
                str(job.connection_id) if job.connection_id else None,
                job.kind,
                job.idempotency_key,
                job.status.value,
                job.error_code,
                job.started_at,
                job.finished_at,
                job.created_at,
            ),
        )
        row = self._fetchone(
            "SELECT job_id FROM ingestion_jobs WHERE tenant_id = %s AND idempotency_key = %s",
            (str(job.tenant_id), job.idempotency_key),
        )
        if row is None or _required_str(row, "job_id") != str(job.job_id):
            raise PersistenceError("ingestion job idempotency conflict")

    def update_ingestion_job(self, job: IngestionJob) -> None:
        self._execute(
            """
            UPDATE ingestion_jobs
            SET status = %s, error_code = %s, started_at = %s, finished_at = %s
            WHERE job_id = %s AND tenant_id = %s
            """,
            (
                job.status.value,
                job.error_code,
                job.started_at,
                job.finished_at,
                str(job.job_id),
                str(job.tenant_id),
            ),
        )
        row = self._fetchone(
            "SELECT job_id FROM ingestion_jobs WHERE job_id = %s AND tenant_id = %s",
            (str(job.job_id), str(job.tenant_id)),
        )
        if row is None:
            raise PersistenceError("ingestion job update target was not found")

    def has_ingestion_checkpoint(
        self, connection_id: str, external_cursor: str
    ) -> bool:
        row = self._fetchone(
            """
            SELECT EXISTS(
                SELECT 1 FROM ingestion_checkpoints
                WHERE connection_id = %s AND external_cursor = %s
            ) AS present
            """,
            (connection_id, external_cursor),
        )
        return bool(row and row.get("present") is True)

    def save_ingestion_checkpoint(self, checkpoint: IngestionCheckpoint) -> None:
        self._execute(
            """
            INSERT INTO ingestion_checkpoints
                (checkpoint_id, tenant_id, connection_id, job_id, external_cursor,
                 content_hash, committed_at)
            SELECT %s, tenant_id, connection_id, job_id, %s, %s, %s
            FROM ingestion_jobs
            WHERE job_id = %s
            ON CONFLICT (connection_id, external_cursor) DO NOTHING
            """,
            (
                checkpoint.checkpoint_id,
                checkpoint.external_cursor,
                checkpoint.content_hash,
                checkpoint.committed_at,
                str(checkpoint.job_id),
            ),
        )
        row = self._fetchone(
            """
            SELECT checkpoint_id, job_id, external_cursor, content_hash
            FROM ingestion_checkpoints WHERE connection_id = %s AND external_cursor = %s
            """,
            (str(checkpoint.connection_id), checkpoint.external_cursor),
        )
        if row is None or (
            _required_str(row, "checkpoint_id") != checkpoint.checkpoint_id
            or _required_str(row, "job_id") != str(checkpoint.job_id)
            or _required_str(row, "external_cursor") != checkpoint.external_cursor
        ):
            raise PersistenceError("ingestion checkpoint idempotency conflict")

    def save_deletion_tombstone(self, tombstone: DeletionTombstone) -> None:
        self._execute(
            """
            INSERT INTO deletion_tombstones
                (tombstone_id, tenant_id, source_type, source_external_id,
                 source_item_id, reason, observed_at, effective_at, retention_until,
                 processed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tombstone_id) DO NOTHING
            """,
            (
                str(tombstone.tombstone_id),
                str(tombstone.tenant_id),
                tombstone.source_type,
                tombstone.source_external_id,
                str(tombstone.source_item_id) if tombstone.source_item_id else None,
                tombstone.reason,
                tombstone.observed_at,
                tombstone.effective_at,
                tombstone.retention_until,
                tombstone.processed_at,
            ),
        )
        row = self._fetchone(
            "SELECT source_type, source_external_id FROM deletion_tombstones WHERE tombstone_id = %s",
            (str(tombstone.tombstone_id),),
        )
        if row is None or (
            _required_str(row, "source_type") != tombstone.source_type
            or _required_str(row, "source_external_id") != tombstone.source_external_id
        ):
            raise PersistenceError("deletion tombstone identity conflict")

    def save_query_trace(self, trace: QueryTraceMetadata) -> None:
        self._execute(
            """
            INSERT INTO query_traces
                (trace_id, tenant_id, principal_subject_id, correlation_id, query_hash,
                 authorization_fingerprint, schema_version, outcome, evidence_ids,
                 latency_ms, created_at, retention_until)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (trace_id) DO NOTHING
            """,
            (
                str(trace.trace_id),
                str(trace.tenant_id),
                trace.principal_subject_id,
                trace.correlation_id,
                trace.query_hash,
                trace.authorization_fingerprint,
                trace.schema_version,
                trace.outcome.value,
                Jsonb(list(trace.evidence_ids)),
                trace.latency_ms,
                trace.created_at,
                trace.retention_until,
            ),
        )

    def save_evaluation_dataset(self, dataset: EvaluationDataset) -> None:
        self._execute(
            """
            INSERT INTO evaluation_datasets (dataset_id, version, description, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (dataset_id) DO UPDATE SET
                version = EXCLUDED.version, description = EXCLUDED.description
            """,
            (
                str(dataset.dataset_id),
                dataset.version,
                dataset.description,
                dataset.created_at,
            ),
        )

    def save_evaluation_case(self, case: EvaluationCase) -> None:
        self._execute(
            """
            INSERT INTO evaluation_cases
                (case_id, dataset_id, case_key, question, expected_evidence_ids, expected_refusal)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (case_id) DO UPDATE SET
                dataset_id = EXCLUDED.dataset_id, case_key = EXCLUDED.case_key,
                question = EXCLUDED.question, expected_evidence_ids = EXCLUDED.expected_evidence_ids,
                expected_refusal = EXCLUDED.expected_refusal
            """,
            (
                str(case.case_id),
                str(case.dataset_id),
                case.case_key,
                case.question,
                Jsonb(list(case.expected_evidence_ids)),
                case.expected_refusal,
            ),
        )

    def save_evaluation_run(self, run: EvaluationRun) -> None:
        self._execute(
            """
            INSERT INTO evaluation_runs
                (run_id, dataset_id, status, model_versions, retrieval_metrics,
                 generation_metrics, started_at, completed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE SET
                status = EXCLUDED.status, model_versions = EXCLUDED.model_versions,
                retrieval_metrics = EXCLUDED.retrieval_metrics,
                generation_metrics = EXCLUDED.generation_metrics,
                completed_at = EXCLUDED.completed_at
            """,
            (
                str(run.run_id),
                str(run.dataset_id),
                run.status.value,
                Jsonb(dict(run.model_versions)),
                Jsonb(dict(run.retrieval_metrics)),
                Jsonb(dict(run.generation_metrics)),
                run.started_at,
                run.completed_at,
            ),
        )

    def get_source_item(self, document_id: str) -> SourceItem | None:
        row = self._fetchone(
            "SELECT * FROM source_items WHERE document_id = %s",
            (document_id,),
        )
        if row is None:
            return None
        account_rows = self._fetchall(
            "SELECT account_id FROM source_item_accounts WHERE document_id = %s ORDER BY account_id",
            (document_id,),
        )
        metadata = _metadata_from_row(row, account_rows)
        return SourceItem(
            document_id=DocumentId(document_id),
            connection_id=SourceConnectionId(_required_str(row, "connection_id")),
            metadata=metadata,
            status=LifecycleStatus(_required_str(row, "status")),
            deleted_at=_optional_datetime(row, "deleted_at"),
            retention_until=_optional_datetime(row, "retention_until"),
            supersedes_document_id=_optional_id(
                row, "supersedes_document_id", document_id
            ),
            lineage=_json_mapping(row, "lineage"),
        )

    def _execute(self, query: str, params: tuple[object, ...]) -> None:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(query, params)
        except psycopg.Error as exc:
            raise PersistenceError("canonical persistence operation failed") from exc

    def _fetchone(
        self, query: str, params: tuple[object, ...]
    ) -> Mapping[str, object] | None:
        try:
            with self._connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
        except psycopg.Error as exc:
            raise PersistenceError("canonical persistence read failed") from exc
        return cast(Mapping[str, object] | None, row)

    def _fetchall(
        self, query: str, params: tuple[object, ...]
    ) -> list[Mapping[str, object]]:
        try:
            with self._connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        except psycopg.Error as exc:
            raise PersistenceError("canonical persistence read failed") from exc
        return [cast(Mapping[str, object], row) for row in rows]


def _required_str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise PersistenceError(f"database field {key} is invalid")
    return value


def _required_int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, int):
        raise PersistenceError(f"database field {key} is invalid")
    return value


def _optional_datetime(row: Mapping[str, object], key: str) -> datetime | None:
    value = row.get(key)
    if value is not None and not isinstance(value, datetime):
        raise PersistenceError(f"database field {key} is invalid")
    return value


def _json_mapping(row: Mapping[str, object], key: str) -> dict[str, str]:
    value = row.get(key)
    if not isinstance(value, dict) or any(
        not isinstance(item_key, str) or not isinstance(item_value, str)
        for item_key, item_value in value.items()
    ):
        raise PersistenceError(f"database field {key} is invalid")
    return dict(value)


def _metadata_from_row(
    row: Mapping[str, object], account_rows: list[Mapping[str, object]]
) -> DocumentMetadata:
    from knowledge_system.domain.persistence import TenantId

    refs = row.get("acl_relationship_refs")
    if not isinstance(refs, list) or any(not isinstance(value, str) for value in refs):
        raise PersistenceError("database ACL relationship references are invalid")
    return DocumentMetadata(
        source_type=_required_str(row, "source_type"),
        source_external_id=_required_str(row, "source_external_id"),
        source_url=cast(str | None, row.get("source_url")),
        tenant_id=TenantId(_required_str(row, "tenant_id")),
        account_ids=tuple(
            AccountId(_required_str(account, "account_id")) for account in account_rows
        ),
        department=cast(str | None, row.get("department")),
        created_at=cast(datetime, row["created_at"]),
        updated_at=cast(datetime, row["updated_at"]),
        author=cast(str | None, row.get("author")),
        classification=Classification(_required_str(row, "classification")),
        external_shareable=bool(row.get("external_shareable")),
        authority_level=_required_int(row, "authority_level"),
        acl_relationship_refs=tuple(refs),
        version=_required_int(row, "version"),
        content_hash=_required_str(row, "content_hash"),
        language=_required_str(row, "language"),
    )


def _optional_id(
    row: Mapping[str, object], key: str, original: str
) -> DocumentId | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise PersistenceError(f"database field {key} is invalid")
    if value == original:
        raise PersistenceError("source item lineage cannot self-reference")
    return DocumentId(value)
