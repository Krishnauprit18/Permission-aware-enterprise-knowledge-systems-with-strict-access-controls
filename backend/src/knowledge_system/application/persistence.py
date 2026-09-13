"""Application services that make transaction boundaries explicit."""

from dataclasses import dataclass

from knowledge_system.application.ports.persistence import (
    CanonicalRepository,
    UnitOfWorkFactory,
)
from knowledge_system.domain.persistence import (
    DeletionTombstone,
    DocumentVersion,
    QueryTraceMetadata,
    SourceItem,
)


@dataclass(slots=True)
class CanonicalPersistenceService:
    """Coordinate one canonical metadata operation per transaction."""

    _unit_of_work: UnitOfWorkFactory

    def save_source_item(self, item: SourceItem) -> None:
        with self._unit_of_work() as repository:
            repository.save_source_item(item)

    def append_document_version(self, version: DocumentVersion) -> None:
        with self._unit_of_work() as repository:
            repository.append_document_version(version)

    def record_deletion(self, tombstone: DeletionTombstone) -> None:
        with self._unit_of_work() as repository:
            repository.save_deletion_tombstone(tombstone)

    def record_query_trace(self, trace: QueryTraceMetadata) -> None:
        with self._unit_of_work() as repository:
            repository.save_query_trace(trace)


def repository_from_uow(repository: CanonicalRepository) -> CanonicalRepository:
    """Keep a named seam for use cases that need several writes atomically."""

    return repository
