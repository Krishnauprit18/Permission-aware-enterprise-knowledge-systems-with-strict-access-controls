"""Application ports for connector ingestion and authorization intent handoff."""

from collections.abc import Callable, Iterable
from typing import Protocol

from knowledge_system.domain.ingestion import (
    AclRelationshipIntent,
    ConnectorFailure,
    RawObjectRef,
    RawSnapshot,
    SourceEnvelope,
)
from knowledge_system.domain.persistence import (
    DeletionTombstone,
    DocumentVersion,
    IngestionCheckpoint,
    IngestionJob,
    SourceConnection,
    SourceItem,
)

ConnectorResult = SourceEnvelope | ConnectorFailure


class Connector(Protocol):
    """Read bounded source changes without making application auth decisions."""

    source_type: str

    def iter_changes(self, checkpoint: str | None) -> Iterable[ConnectorResult]: ...


class RawObjectStore(Protocol):
    """Persist source bytes before any future parsing or derivative creation."""

    def put(self, snapshot: RawSnapshot) -> RawObjectRef: ...


class RawObjectReader(Protocol):
    """Read a bounded raw snapshot after a caller verifies canonical metadata."""

    def get(
        self,
        object_uri: str,
        *,
        expected_content_hash: str,
        max_bytes: int,
    ) -> bytes: ...


class AuthorizationRelationshipSink(Protocol):
    """Apply or remove mapped relationship intents in a dedicated adapter boundary."""

    def apply(self, intents: tuple[AclRelationshipIntent, ...]) -> None: ...

    def remove(self, resource_id: str, tenant_id: str) -> None: ...


class IngestionPersistence(Protocol):
    """Persistence facade that owns one explicit transaction per operation."""

    def prepare_run(self, connection: SourceConnection, job: IngestionJob) -> None: ...

    def get_source_item(self, document_id: str) -> SourceItem | None: ...

    def has_checkpoint(self, connection_id: str, external_cursor: str) -> bool: ...

    def persist_metadata(
        self, item: SourceItem, version: DocumentVersion | None
    ) -> None: ...

    def persist_tombstone(self, tombstone: DeletionTombstone) -> None: ...

    def persist_checkpoint(self, checkpoint: IngestionCheckpoint) -> None: ...

    def finalize_run(self, job: IngestionJob) -> None: ...


Sleeper = Callable[[float], None]
