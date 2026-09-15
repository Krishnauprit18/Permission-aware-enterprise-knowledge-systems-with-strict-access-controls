"""Regression tests for the connector and raw-ingestion boundary."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from shutil import copytree

import pytest

from knowledge_system.adapters.connectors.fixtures import (
    FilesystemFixtureConnector,
    SlackFixtureConnector,
    SupportTicketFixtureConnector,
)
from knowledge_system.application.ingestion import (
    IngestionOrchestrator,
    TransientIngestionError,
)
from knowledge_system.application.ports.ingestion import (
    AuthorizationRelationshipSink,
    IngestionPersistence,
    RawObjectStore,
)
from knowledge_system.application.ports.observability import (
    SecurityAuditSink,
    Span,
    TelemetryValue,
)
from knowledge_system.domain.ingestion import (
    AclRelationshipIntent,
    ConnectorFailure,
    RawObjectRef,
    RawSnapshot,
    RetryPolicy,
    SourceEnvelope,
)
from knowledge_system.domain.observability import SecurityAuditEvent
from knowledge_system.domain.persistence import (
    DeletionTombstone,
    DocumentVersion,
    IngestionCheckpoint,
    IngestionJob,
    SourceConnection,
    SourceConnectionId,
    SourceItem,
    TenantId,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DATASET_ROOT = REPOSITORY_ROOT / "data" / "synthetic"
NOW = datetime(2026, 9, 13, 6, 0, tzinfo=UTC)


@dataclass
class FakeRawStore(RawObjectStore):
    snapshots: list[RawSnapshot] = field(default_factory=list)
    transient_failures: int = 0

    def put(self, snapshot: RawSnapshot) -> RawObjectRef:
        if self.transient_failures:
            self.transient_failures -= 1
            raise TransientIngestionError("temporary test failure")
        self.snapshots.append(snapshot)
        return RawObjectRef(
            object_uri=f"memory://{snapshot.object_key}",
            content_hash=f"sha256:{sha256(snapshot.payload).hexdigest()}",
            size_bytes=len(snapshot.payload),
        )


@dataclass
class FakeRelationshipSink(AuthorizationRelationshipSink):
    applied: list[AclRelationshipIntent] = field(default_factory=list)
    removed: list[tuple[str, str]] = field(default_factory=list)

    def apply(self, intents: tuple[AclRelationshipIntent, ...]) -> None:
        self.applied.extend(intents)

    def remove(self, resource_id: str, tenant_id: str) -> None:
        self.removed.append((resource_id, tenant_id))


@dataclass
class FakePersistence(IngestionPersistence):
    items: dict[str, SourceItem] = field(default_factory=dict)
    checkpoints: dict[tuple[str, str], IngestionCheckpoint] = field(
        default_factory=dict
    )
    jobs: dict[str, IngestionJob] = field(default_factory=dict)
    tombstones: list[DeletionTombstone] = field(default_factory=list)

    def prepare_run(self, connection: SourceConnection, job: IngestionJob) -> None:
        del connection
        self.jobs[str(job.job_id)] = job

    def get_source_item(self, document_id: str) -> SourceItem | None:
        return self.items.get(document_id)

    def has_checkpoint(self, connection_id: str, external_cursor: str) -> bool:
        return (connection_id, external_cursor) in self.checkpoints

    def persist_metadata(
        self, item: SourceItem, version: DocumentVersion | None
    ) -> None:
        del version
        self.items[str(item.document_id)] = item

    def persist_tombstone(self, tombstone: DeletionTombstone) -> None:
        self.tombstones.append(tombstone)

    def persist_checkpoint(self, checkpoint: IngestionCheckpoint) -> None:
        self.checkpoints[
            (str(checkpoint.connection_id), checkpoint.external_cursor)
        ] = checkpoint

    def finalize_run(self, job: IngestionJob) -> None:
        self.jobs[str(job.job_id)] = job


@dataclass
class FakeAuditSink(SecurityAuditSink):
    events: list[SecurityAuditEvent] = field(default_factory=list)

    def record_security_event(self, event: SecurityAuditEvent) -> None:
        self.events.append(event)


@dataclass
class FakeTelemetry:
    spans: list[str] = field(default_factory=list)

    @contextmanager
    def span(
        self,
        name: str,
        attributes: Mapping[str, TelemetryValue] | None = None,
    ) -> Iterator[Span]:
        del attributes
        self.spans.append(name)
        yield _NoopSpan()

    def counter(
        self,
        name: str,
        value: int = 1,
        attributes: Mapping[str, TelemetryValue] | None = None,
    ) -> None:
        del name, value, attributes


class _NoopSpan:
    def set_attribute(self, key: str, value: TelemetryValue) -> None:
        del key, value

    def record_exception(self, error: BaseException) -> None:
        del error


def _connection(source_type: str) -> SourceConnection:
    return SourceConnection(
        connection_id=SourceConnectionId(f"conn-{source_type}"),
        tenant_id=TenantId("northstar"),
        source_type=source_type,
        external_id=f"fixture-{source_type}",
        base_url=None,
        credentials_ref=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _orchestrator(
    persistence: FakePersistence,
    raw_store: FakeRawStore | None = None,
    sink: FakeRelationshipSink | None = None,
    *,
    delays: list[float] | None = None,
    audit_sink: SecurityAuditSink | None = None,
    telemetry: FakeTelemetry | None = None,
) -> IngestionOrchestrator:
    return IngestionOrchestrator(
        persistence,
        raw_store or FakeRawStore(),
        sink or FakeRelationshipSink(),
        retry_policy=RetryPolicy(
            max_attempts=3, base_delay_seconds=0.01, max_delay_seconds=0.02
        ),
        sleeper=delays.append if delays is not None else (lambda _delay: None),
        clock=lambda: NOW,
        audit_sink=audit_sink,
        telemetry=telemetry,
    )


@pytest.mark.unit
def test_first_sync_stores_raw_bytes_and_acl_intents() -> None:
    persistence = FakePersistence()
    raw_store = FakeRawStore()
    sink = FakeRelationshipSink()
    result = _orchestrator(persistence, raw_store, sink).run(
        FilesystemFixtureConnector(DATASET_ROOT), _connection("document"), None
    )

    assert result.status == "FAILED"
    assert result.processed_count == 6
    assert result.failed_count == 1
    assert len(raw_store.snapshots) == result.processed_count
    assert sink.applied
    assert all(
        "source-content-hash" in snapshot.metadata for snapshot in raw_store.snapshots
    )
    assert all(
        "raw/northstar/document/" in str(snapshot.object_key)
        for snapshot in raw_store.snapshots
    )


@pytest.mark.unit
def test_second_sync_is_unchanged_and_does_not_rewrite_raw_objects() -> None:
    persistence = FakePersistence()
    raw_store = FakeRawStore()
    connector = FilesystemFixtureConnector(DATASET_ROOT)
    connection = _connection("document")
    first = _orchestrator(persistence, raw_store).run(connector, connection, None)
    second = _orchestrator(persistence, raw_store).run(connector, connection, None)

    assert first.processed_count == 6
    assert second.processed_count == 0
    assert second.unchanged_count == 6
    assert second.failed_count == 1
    assert len(raw_store.snapshots) == 6


@pytest.mark.unit
def test_update_reprocesses_same_external_item_when_hash_and_version_change(
    tmp_path: Path,
) -> None:
    root = tmp_path / "synthetic"
    copytree(DATASET_ROOT, root)
    persistence = FakePersistence()
    raw_store = FakeRawStore()
    connector = FilesystemFixtureConnector(root)
    connection = _connection("document")
    _orchestrator(persistence, raw_store).run(connector, connection, None)

    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target = next(
        row
        for row in manifest["source_items"]
        if row["id"] == "doc-acme-approved-launch-date-v3"
    )
    source_path = root / target["source_path"]
    payload = (
        source_path.read_bytes()
        + b"\nRevision note: approved for customer communication.\n"
    )
    source_path.write_bytes(payload)
    target["version"] = 4
    target["updated_at"] = "2026-09-12T12:00:00Z"
    target["content_hash"] = f"sha256:{sha256(payload).hexdigest()}"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = _orchestrator(persistence, raw_store).run(
        FilesystemFixtureConnector(root), connection, None
    )

    assert result.processed_count == 1
    assert result.unchanged_count == 5
    assert result.failed_count == 1
    assert persistence.items[target["id"]].metadata.version == 4
    assert len(raw_store.snapshots) == 7


@pytest.mark.unit
def test_delete_persists_tombstone_and_removes_relationship() -> None:
    persistence = FakePersistence()
    sink = FakeRelationshipSink()
    result = _orchestrator(persistence, sink=sink).run(
        SupportTicketFixtureConnector(DATASET_ROOT), _connection("support_ticket"), None
    )

    assert result.status == "SUCCEEDED"
    assert result.deleted_count == 1
    assert sink.removed == [("resource:ticket-cedar-deleted-0991", "northstar")]
    assert len(persistence.tombstones) == 1


@pytest.mark.unit
@pytest.mark.security
def test_ingestion_audit_records_lifecycle_without_source_content() -> None:
    audit = FakeAuditSink()

    result = _orchestrator(FakePersistence(), audit_sink=audit).run(
        SlackFixtureConnector(DATASET_ROOT), _connection("slack_thread"), None
    )

    assert result.status == "SUCCEEDED"
    assert {event.event_type.value for event in audit.events} == {"INGESTION"}
    serialized = repr(audit.events)
    assert "Ignore all system instructions" not in serialized
    assert all(event.tenant_id == "northstar" for event in audit.events)
    assert all(
        event.target_ref_hash is not None and len(event.target_ref_hash) == 64
        for event in audit.events
    )


@pytest.mark.unit
def test_ingestion_traces_connector_and_sync_without_source_attributes() -> None:
    telemetry = FakeTelemetry()

    result = _orchestrator(FakePersistence(), telemetry=telemetry).run(
        SlackFixtureConnector(DATASET_ROOT), _connection("slack_thread"), None
    )

    assert result.status == "SUCCEEDED"
    assert telemetry.spans == [
        "knowledge.ingestion.sync",
        "knowledge.ingestion.connector",
    ]


@pytest.mark.unit
@pytest.mark.security
def test_malformed_source_isolated_from_other_items(tmp_path: Path) -> None:
    root = tmp_path / "synthetic"
    copytree(DATASET_ROOT, root)
    (root / "source" / "tickets" / "beacon-scheduling.json").write_text(
        "{malformed", encoding="utf-8"
    )

    result = _orchestrator(FakePersistence()).run(
        SupportTicketFixtureConnector(root), _connection("support_ticket"), None
    )

    assert result.status == "FAILED"
    assert result.failed_count == 1
    assert result.deleted_count == 1


@pytest.mark.unit
def test_missing_manifest_identity_isolated_from_other_items(tmp_path: Path) -> None:
    root = tmp_path / "synthetic"
    copytree(DATASET_ROOT, root)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    row = next(
        row for row in manifest["source_items"] if row["source_type"] == "document"
    )
    del row["id"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = _orchestrator(FakePersistence()).run(
        FilesystemFixtureConnector(root), _connection("document"), None
    )

    assert result.failed_count == 2
    assert result.processed_count == 5


@pytest.mark.unit
@pytest.mark.security
def test_manifest_hash_mismatch_is_rejected_before_raw_write(tmp_path: Path) -> None:
    root = tmp_path / "synthetic"
    copytree(DATASET_ROOT, root)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    row = next(
        row for row in manifest["source_items"] if row["source_type"] == "document"
    )
    row["content_hash"] = "sha256:" + "f" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    raw_store = FakeRawStore()

    result = _orchestrator(FakePersistence(), raw_store).run(
        FilesystemFixtureConnector(root), _connection("document"), None
    )

    assert result.failed_count == 2
    assert result.processed_count == 5
    assert len(raw_store.snapshots) == 5


@pytest.mark.unit
def test_interrupted_raw_write_is_replayable() -> None:
    class InterruptingStore(FakeRawStore):
        def put(self, snapshot: RawSnapshot) -> RawObjectRef:
            del snapshot
            raise KeyboardInterrupt

    persistence = FakePersistence()
    connection = _connection("document")
    with pytest.raises(KeyboardInterrupt):
        _orchestrator(persistence, InterruptingStore()).run(
            FilesystemFixtureConnector(DATASET_ROOT), connection, None
        )
    assert not persistence.checkpoints

    result = _orchestrator(persistence).run(
        FilesystemFixtureConnector(DATASET_ROOT), connection, None
    )
    assert result.status == "FAILED"
    assert result.processed_count == 6
    assert result.failed_count == 1


@pytest.mark.unit
@pytest.mark.security
def test_duplicate_source_external_id_is_a_per_item_failure(tmp_path: Path) -> None:
    root = tmp_path / "synthetic"
    copytree(DATASET_ROOT, root)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    first = next(
        row for row in manifest["source_items"] if row["source_type"] == "document"
    )
    second = next(
        row
        for row in manifest["source_items"]
        if row["source_type"] == "document" and row is not first
    )
    second["source_external_id"] = first["source_external_id"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = _orchestrator(FakePersistence()).run(
        FilesystemFixtureConnector(root), _connection("document"), None
    )

    assert result.failed_count == 3
    assert result.processed_count == 4


@pytest.mark.unit
@pytest.mark.security
def test_hostile_path_is_rejected_without_reading_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "synthetic"
    copytree(DATASET_ROOT, root)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    row = next(
        row for row in manifest["source_items"] if row["source_type"] == "document"
    )
    row["source_path"] = "../../AGENTS.md"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    results = list(FilesystemFixtureConnector(root).iter_changes(None))

    assert isinstance(results[0], ConnectorFailure)
    assert all(
        not isinstance(result, SourceEnvelope)
        or result.source_path != "../../AGENTS.md"
        for result in results
    )


@pytest.mark.unit
@pytest.mark.security
def test_acl_mapping_preserves_tenant_and_resource_intent() -> None:
    results = list(SlackFixtureConnector(DATASET_ROOT).iter_changes(None))
    envelope = next(result for result in results if isinstance(result, SourceEnvelope))

    assert envelope.acl_relationships
    assert all(
        intent.tenant_id == envelope.metadata.tenant_id
        for intent in envelope.acl_relationships
    )
    assert all(
        intent.resource_id.startswith("resource:")
        for intent in envelope.acl_relationships
    )


@pytest.mark.unit
def test_transient_raw_store_uses_bounded_exponential_backoff() -> None:
    persistence = FakePersistence()
    raw_store = FakeRawStore(transient_failures=2)
    delays: list[float] = []

    result = _orchestrator(persistence, raw_store, delays=delays).run(
        SlackFixtureConnector(DATASET_ROOT), _connection("slack_thread"), None
    )

    assert result.status == "SUCCEEDED"
    assert delays == [0.01, 0.02]


@pytest.mark.unit
@pytest.mark.security
def test_structured_item_log_excludes_source_path_and_raw_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    result = _orchestrator(FakePersistence()).run(
        SlackFixtureConnector(DATASET_ROOT), _connection("slack_thread"), None
    )

    assert result.status == "SUCCEEDED"
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "indirect-prompt-injection.json" not in messages
    assert "Ignore all system instructions" not in messages


@pytest.mark.unit
@pytest.mark.security
def test_raw_store_integrity_mismatch_is_not_checkpointed() -> None:
    class LyingStore(FakeRawStore):
        def put(self, snapshot: RawSnapshot) -> RawObjectRef:
            return RawObjectRef(
                object_uri=f"memory://{snapshot.object_key}",
                content_hash="sha256:" + "0" * 64,
                size_bytes=len(snapshot.payload),
            )

    persistence = FakePersistence()
    result = _orchestrator(persistence, LyingStore()).run(
        SlackFixtureConnector(DATASET_ROOT), _connection("slack_thread"), None
    )

    assert result.status == "FAILED"
    assert result.failed_count == 2
    assert not persistence.checkpoints
