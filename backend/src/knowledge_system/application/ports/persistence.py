"""Typed persistence ports; infrastructure remains outside application code."""

from collections.abc import Callable
from typing import Literal, Protocol

from knowledge_system.domain.persistence import (
    Account,
    ChunkMetadata,
    DeletionTombstone,
    DocumentVersion,
    EvaluationCase,
    EvaluationDataset,
    EvaluationRun,
    IngestionCheckpoint,
    IngestionJob,
    PrincipalReference,
    QueryTraceMetadata,
    SourceConnection,
    SourceItem,
    Tenant,
)


class PersistenceError(RuntimeError):
    """A persistence operation could not be completed."""


class CanonicalRepository(Protocol):
    """Repository operations for canonical control metadata."""

    def save_tenant(self, tenant: Tenant) -> None: ...

    def save_principal_reference(self, principal: PrincipalReference) -> None: ...

    def save_account(self, account: Account) -> None: ...

    def save_source_connection(self, connection: SourceConnection) -> None: ...

    def save_source_item(self, item: SourceItem) -> None: ...

    def append_document_version(self, version: DocumentVersion) -> None: ...

    def save_chunk_metadata(self, chunk: ChunkMetadata) -> None: ...

    def save_ingestion_job(self, job: IngestionJob) -> None: ...

    def save_ingestion_checkpoint(self, checkpoint: IngestionCheckpoint) -> None: ...

    def save_deletion_tombstone(self, tombstone: DeletionTombstone) -> None: ...

    def save_query_trace(self, trace: QueryTraceMetadata) -> None: ...

    def save_evaluation_dataset(self, dataset: EvaluationDataset) -> None: ...

    def save_evaluation_case(self, case: EvaluationCase) -> None: ...

    def save_evaluation_run(self, run: EvaluationRun) -> None: ...

    def get_source_item(self, document_id: str) -> SourceItem | None: ...


class UnitOfWork(Protocol):
    """A repository transaction with commit/rollback owned by the adapter."""

    repository: CanonicalRepository

    def __enter__(self) -> CanonicalRepository: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> Literal[False]: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
