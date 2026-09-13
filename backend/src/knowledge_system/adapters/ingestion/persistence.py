"""PostgreSQL transaction adapter for ingestion operations."""

from knowledge_system.application.ports.ingestion import IngestionPersistence
from knowledge_system.application.ports.persistence import UnitOfWorkFactory
from knowledge_system.domain.persistence import (
    DeletionTombstone,
    DocumentVersion,
    IngestionCheckpoint,
    IngestionJob,
    SourceConnection,
    SourceItem,
)


class PostgresIngestionPersistence(IngestionPersistence):
    """Keep each ingestion persistence operation in an explicit transaction."""

    def __init__(self, unit_of_work: UnitOfWorkFactory) -> None:
        self._unit_of_work = unit_of_work

    def prepare_run(self, connection: SourceConnection, job: IngestionJob) -> None:
        with self._unit_of_work() as repository:
            repository.save_source_connection(connection)
            repository.save_ingestion_job(job)

    def get_source_item(self, document_id: str) -> SourceItem | None:
        with self._unit_of_work() as repository:
            return repository.get_source_item(document_id)

    def has_checkpoint(self, connection_id: str, external_cursor: str) -> bool:
        with self._unit_of_work() as repository:
            return repository.has_ingestion_checkpoint(connection_id, external_cursor)

    def persist_metadata(
        self, item: SourceItem, version: DocumentVersion | None
    ) -> None:
        with self._unit_of_work() as repository:
            repository.save_source_item(item)
            if version is not None:
                repository.append_document_version(version)

    def persist_tombstone(self, tombstone: DeletionTombstone) -> None:
        with self._unit_of_work() as repository:
            repository.save_deletion_tombstone(tombstone)

    def persist_checkpoint(self, checkpoint: IngestionCheckpoint) -> None:
        with self._unit_of_work() as repository:
            repository.save_ingestion_checkpoint(checkpoint)

    def finalize_run(self, job: IngestionJob) -> None:
        with self._unit_of_work() as repository:
            repository.update_ingestion_job(job)
