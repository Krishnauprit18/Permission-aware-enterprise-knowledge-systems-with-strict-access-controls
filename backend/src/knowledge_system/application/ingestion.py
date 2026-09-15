"""Permission-neutral ingestion orchestration before parsing or indexing."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from time import sleep

from knowledge_system.application.audit import lifecycle_event
from knowledge_system.application.ports.ingestion import (
    AuthorizationRelationshipSink,
    Connector,
    ConnectorResult,
    IngestionPersistence,
    RawObjectStore,
    Sleeper,
)
from knowledge_system.application.ports.observability import (
    BestEffortTelemetry,
    NoopTelemetry,
    SecurityAuditSink,
    TelemetryPort,
)
from knowledge_system.application.ports.persistence import PersistenceError
from knowledge_system.domain.ingestion import (
    ConnectorFailure,
    IngestionResult,
    RawObjectKey,
    RawObjectRef,
    RawSnapshot,
    RetryPolicy,
    SourceEnvelope,
)
from knowledge_system.domain.observability import (
    AuditEventType,
    AuditOutcome,
    SecurityAuditEvent,
)
from knowledge_system.domain.persistence import (
    DeletionTombstone,
    DeletionTombstoneId,
    DocumentVersion,
    DocumentVersionId,
    IngestionCheckpoint,
    IngestionJob,
    IngestionJobId,
    IngestionJobStatus,
    LifecycleStatus,
    SourceConnection,
    SourceItem,
)

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class IngestionError(RuntimeError):
    """A safe, categorized ingestion failure."""

    error_code = "INGESTION_ERROR"


class TransientIngestionError(IngestionError):
    """An operation may succeed when retried."""

    error_code = "TRANSIENT_FAILURE"


class PermanentIngestionError(IngestionError):
    """Retrying the same input or operation cannot safely fix it."""

    error_code = "PERMANENT_FAILURE"


class RetryExhaustedError(TransientIngestionError):
    """A bounded retry budget was consumed."""

    error_code = "RETRY_EXHAUSTED"


Clock = Callable[[], datetime]


class IngestionOrchestrator:
    """Coordinate safe raw handoff, metadata, ACL intents, and checkpoints."""

    def __init__(
        self,
        persistence: IngestionPersistence,
        raw_store: RawObjectStore,
        relationship_sink: AuthorizationRelationshipSink,
        *,
        retry_policy: RetryPolicy | None = None,
        sleeper: Sleeper | None = None,
        clock: Clock | None = None,
        logger: logging.Logger | None = None,
        telemetry: TelemetryPort | None = None,
        audit_sink: SecurityAuditSink | None = None,
    ) -> None:
        self._persistence = persistence
        self._raw_store = raw_store
        self._relationship_sink = relationship_sink
        self._retry_policy = retry_policy or RetryPolicy()
        self._sleeper = sleeper or sleep
        self._clock = clock or (lambda: datetime.now(UTC))
        self._logger = logger or logging.getLogger(__name__)
        self._telemetry = BestEffortTelemetry(telemetry or NoopTelemetry())
        self._audit_sink = audit_sink

    def run(
        self,
        connector: Connector,
        connection: SourceConnection,
        checkpoint: str | None,
    ) -> IngestionResult:
        """Run a sync inside a content-free, correlation-safe telemetry span."""

        with self._telemetry.span(
            "knowledge.ingestion.sync",
            {
                "tenant.id": str(connection.tenant_id),
                "source.type": connection.source_type,
                "source.connection_id": str(connection.connection_id),
            },
        ) as span:
            try:
                result = self._run(connector, connection, checkpoint)
            except BaseException as error:
                span.record_exception(error)
                self._telemetry.counter("knowledge.ingestion.failures")
                self._emit_audit(
                    lifecycle_event(
                        AuditEventType.INGESTION,
                        correlation_id=f"ingestion:{connection.connection_id}",
                        outcome=AuditOutcome.FAILED,
                        reason_code="sync_failed",
                        tenant_id=str(connection.tenant_id),
                        target_ref=str(connection.connection_id),
                    )
                )
                raise
            self._telemetry.counter(
                "knowledge.ingestion.completed",
                attributes={"status": result.status},
            )
            self._emit_audit(
                lifecycle_event(
                    AuditEventType.INGESTION,
                    correlation_id=result.trace_id,
                    outcome=(
                        AuditOutcome.SUCCEEDED
                        if result.status == "SUCCEEDED"
                        else AuditOutcome.FAILED
                    ),
                    reason_code=(
                        "sync_completed"
                        if result.status == "SUCCEEDED"
                        else "item_failures"
                    ),
                    tenant_id=str(connection.tenant_id),
                    target_ref=str(connection.connection_id),
                    attributes={
                        "job_id": result.job_id,
                        "processed_count": result.processed_count,
                        "unchanged_count": result.unchanged_count,
                        "failed_count": result.failed_count,
                        "deleted_count": result.deleted_count,
                    },
                )
            )
            if result.deleted_count:
                self._emit_audit(
                    lifecycle_event(
                        AuditEventType.DELETION,
                        correlation_id=result.trace_id,
                        outcome=AuditOutcome.SUCCEEDED,
                        reason_code="source_deletions_recorded",
                        tenant_id=str(connection.tenant_id),
                        target_ref=str(connection.connection_id),
                        attributes={"deleted_count": result.deleted_count},
                    )
                )
            return result

    def _emit_audit(self, event: SecurityAuditEvent) -> None:
        if self._audit_sink is None:
            return
        try:
            self._audit_sink.record_security_event(event)
        except (OSError, RuntimeError, ValueError):
            self._telemetry.counter("knowledge.audit.write_failures")

    def _run(
        self,
        connector: Connector,
        connection: SourceConnection,
        checkpoint: str | None,
    ) -> IngestionResult:
        """Run one source sync; only successful item work is checkpointed."""

        if connector.source_type != connection.source_type:
            raise PermanentIngestionError("connector source type mismatch")
        job_id = _stable_id(
            "job_", f"{connection.connection_id}|{checkpoint or 'initial'}", 32
        )
        trace_id = _stable_id("trace_ingest_", str(job_id), 32)
        started_at = self._clock()
        job = IngestionJob(
            job_id=IngestionJobId(job_id),
            tenant_id=connection.tenant_id,
            connection_id=connection.connection_id,
            kind="sync",
            idempotency_key=f"sync:{connection.connection_id}:{checkpoint or 'initial'}",
            created_at=started_at,
            status=IngestionJobStatus.RUNNING,
            started_at=started_at,
        )
        self._persistence.prepare_run(connection, job)
        processed = unchanged = failed = deleted = 0
        last_cursor: str | None = None
        gap = False
        try:
            for result in self._iter_connector_changes(
                connector, checkpoint, connection
            ):
                cursor = result.external_cursor
                if isinstance(result, ConnectorFailure):
                    failed += 1
                    gap = True
                    self._log_item(
                        job_id, trace_id, result.document_id, cursor, result.error_code
                    )
                    continue
                try:
                    item_processed, item_deleted, item_unchanged = self._process_item(
                        result, connection, job_id, trace_id
                    )
                except (
                    IngestionError,
                    KeyError,
                    OSError,
                    PersistenceError,
                    TypeError,
                    ValueError,
                ):
                    failed += 1
                    gap = True
                    self._log_item(
                        job_id,
                        trace_id,
                        str(result.document_id),
                        cursor,
                        "ITEM_PROCESSING_FAILED",
                    )
                    continue
                processed += item_processed
                deleted += item_deleted
                unchanged += item_unchanged
                if not gap:
                    last_cursor = cursor
            status = (
                IngestionJobStatus.FAILED if failed else IngestionJobStatus.SUCCEEDED
            )
            final_job = replace(
                job,
                status=status,
                error_code="ITEM_FAILURES" if failed else None,
                finished_at=self._clock(),
            )
            self._persistence.finalize_run(final_job)
            return IngestionResult(
                job_id=job_id,
                trace_id=trace_id,
                processed_count=processed,
                unchanged_count=unchanged,
                failed_count=failed,
                deleted_count=deleted,
                last_cursor=last_cursor,
                status=status.value,
            )
        except Exception:
            failed += 1
            final_job = replace(
                job,
                status=IngestionJobStatus.FAILED,
                error_code="CONNECTOR_RUN_FAILED",
                finished_at=self._clock(),
            )
            self._persistence.finalize_run(final_job)
            raise

    def _iter_connector_changes(
        self,
        connector: Connector,
        checkpoint: str | None,
        connection: SourceConnection,
    ) -> Iterator[ConnectorResult]:
        """Trace connector I/O without attaching source content or item IDs."""

        with self._telemetry.span(
            "knowledge.ingestion.connector",
            {
                "tenant.id": str(connection.tenant_id),
                "source.type": connector.source_type,
            },
        ):
            yield from connector.iter_changes(checkpoint)

    def _process_item(
        self,
        envelope: SourceEnvelope,
        connection: SourceConnection,
        job_id: str,
        trace_id: str,
    ) -> tuple[int, int, int]:
        if envelope.metadata.tenant_id != connection.tenant_id:
            raise PermanentIngestionError("source tenant mismatch")
        existing = self._persistence.get_source_item(str(envelope.document_id))
        if existing is not None and existing.metadata.tenant_id != connection.tenant_id:
            raise PermanentIngestionError("source item tenant mismatch")
        if self._is_unchanged(existing, envelope) and self._persistence.has_checkpoint(
            str(connection.connection_id), envelope.external_cursor
        ):
            self._log_item(
                job_id,
                trace_id,
                str(envelope.document_id),
                envelope.external_cursor,
                "UNCHANGED",
            )
            return 0, 0, 1
        if (
            existing is not None
            and existing.status is LifecycleStatus.DELETED
            and not envelope.is_deleted
        ):
            raise PermanentIngestionError("stale resurrection blocked")
        if not envelope.is_deleted:
            if envelope.raw_content is None:
                raise PermanentIngestionError("active item has no raw content")
            primary_ref = self._put_raw(
                envelope,
                envelope.raw_content,
                f"{connection.connection_id}/primary",
                trace_id,
                is_primary=True,
            )
            for attachment in envelope.attachments:
                if attachment.content is not None:
                    self._put_raw(
                        envelope,
                        attachment.content,
                        f"{connection.connection_id}/attachment/{attachment.name}",
                        trace_id,
                        is_primary=False,
                    )
            item = self._source_item(envelope, connection, LifecycleStatus.ACTIVE)
            previous_version = existing.metadata.version if existing else None
            version = DocumentVersion(
                version_id=DocumentVersionId(
                    f"{envelope.document_id}-v{envelope.metadata.version}"
                ),
                document_id=envelope.document_id,
                version=envelope.metadata.version,
                content_hash=envelope.metadata.content_hash,
                raw_object_ref=primary_ref.object_uri,
                created_at=envelope.metadata.updated_at,
                supersedes_version_id=(
                    DocumentVersionId(f"{envelope.document_id}-v{previous_version}")
                    if previous_version is not None
                    and previous_version != envelope.metadata.version
                    else None
                ),
            )
            self._persistence.persist_metadata(item, version)
            self._relationship_sink.apply(envelope.acl_relationships)
            processed = 1
            deleted_count = 0
        else:
            item = self._source_item(envelope, connection, LifecycleStatus.DELETED)
            self._persistence.persist_metadata(item, None)
            self._relationship_sink.remove(
                f"resource:{envelope.document_id}", str(connection.tenant_id)
            )
            tombstone = DeletionTombstone(
                tombstone_id=DeletionTombstoneId(
                    _stable_id(
                        "tombstone_",
                        f"{connection.tenant_id}|{envelope.metadata.source_type}|"
                        f"{envelope.metadata.source_external_id}",
                        32,
                    )
                ),
                tenant_id=connection.tenant_id,
                source_type=envelope.metadata.source_type,
                source_external_id=envelope.metadata.source_external_id,
                source_item_id=envelope.document_id,
                reason="source_deleted",
                observed_at=self._clock(),
                effective_at=self._clock(),
                retention_until=self._clock()
                + timedelta(days=connection.retention_days or 30),
            )
            self._persistence.persist_tombstone(tombstone)
            processed = 1
            deleted_count = 1
        self._persistence.persist_checkpoint(
            IngestionCheckpoint(
                checkpoint_id=_stable_id(
                    "checkpoint_",
                    f"{connection.connection_id}|{envelope.external_cursor}",
                    32,
                ),
                connection_id=connection.connection_id,
                job_id=IngestionJobId(job_id),
                external_cursor=envelope.external_cursor,
                content_hash=envelope.metadata.content_hash,
                committed_at=self._clock(),
            )
        )
        self._log_item(
            job_id,
            trace_id,
            str(envelope.document_id),
            envelope.external_cursor,
            "DELETED" if envelope.is_deleted else "PROCESSED",
        )
        return processed, deleted_count, 0

    def _put_raw(
        self,
        envelope: SourceEnvelope,
        payload: bytes,
        purpose: str,
        trace_id: str,
        *,
        is_primary: bool,
    ) -> RawObjectRef:
        expected_hash = f"sha256:{sha256(payload).hexdigest()}"
        if is_primary and expected_hash != envelope.metadata.content_hash:
            raise PermanentIngestionError("raw payload hash does not match metadata")
        if not _SHA256_RE.fullmatch(expected_hash):
            raise PermanentIngestionError("content hash format is invalid")
        if not payload:
            raise PermanentIngestionError("raw payload is empty")
        key = RawObjectKey(
            "raw/"
            f"{envelope.metadata.tenant_id}/"
            f"{envelope.metadata.source_type}/"
            f"{sha256(str(envelope.document_id).encode('utf-8')).hexdigest()[:32]}/"
            f"v{envelope.metadata.version}/"
            f"{expected_hash.removeprefix('sha256:')}/"
            f"{sha256(purpose.encode('utf-8')).hexdigest()[:16]}.bin"
        )
        reference = self._retry(
            lambda: self._raw_store.put(
                RawSnapshot(
                    object_key=key,
                    payload=payload,
                    content_type=envelope.content_type,
                    metadata={
                        "trace-id": trace_id,
                        "tenant-id": str(envelope.metadata.tenant_id),
                        "source-type": envelope.metadata.source_type,
                        "source-external-id": envelope.metadata.source_external_id,
                        "source-version": str(envelope.metadata.version),
                        "source-content-hash": envelope.metadata.content_hash,
                        "source-cursor": envelope.external_cursor,
                        "snapshot-purpose": purpose,
                        "snapshot-content-hash": expected_hash,
                    },
                )
            )
        )
        if reference.content_hash != expected_hash or reference.size_bytes != len(
            payload
        ):
            raise PermanentIngestionError("raw object integrity verification failed")
        return reference

    def _retry(self, operation: Callable[[], RawObjectRef]) -> RawObjectRef:
        for attempt in range(1, self._retry_policy.max_attempts + 1):
            try:
                return operation()
            except PermanentIngestionError:
                raise
            except TransientIngestionError as exc:
                if attempt == self._retry_policy.max_attempts:
                    raise RetryExhaustedError from exc
                delay = min(
                    self._retry_policy.max_delay_seconds,
                    self._retry_policy.base_delay_seconds * (2 ** (attempt - 1)),
                )
                self._sleeper(delay)
        raise RetryExhaustedError

    def _source_item(
        self,
        envelope: SourceEnvelope,
        connection: SourceConnection,
        status: LifecycleStatus,
    ) -> SourceItem:
        deleted_at = self._clock() if status is LifecycleStatus.DELETED else None
        return SourceItem(
            document_id=envelope.document_id,
            connection_id=connection.connection_id,
            metadata=envelope.metadata,
            status=status,
            deleted_at=deleted_at,
            retention_until=(
                deleted_at + timedelta(days=connection.retention_days or 30)
                if deleted_at is not None
                else None
            ),
            supersedes_document_id=envelope.supersedes_document_id,
            lineage={
                "source_cursor": envelope.external_cursor,
                "source_connection": str(connection.connection_id),
            },
        )

    @staticmethod
    def _is_unchanged(existing: SourceItem | None, envelope: SourceEnvelope) -> bool:
        return existing is not None and (
            existing.metadata.content_hash == envelope.metadata.content_hash
            and existing.metadata.version == envelope.metadata.version
            and existing.status
            == (
                LifecycleStatus.DELETED
                if envelope.is_deleted
                else LifecycleStatus.ACTIVE
            )
        )

    def _log_item(
        self,
        job_id: str,
        trace_id: str,
        document_id: str,
        cursor: str,
        outcome: str,
    ) -> None:
        self._logger.info(
            "ingestion_item",
            extra={
                "job_id": job_id,
                "trace_id": trace_id,
                "document_id": document_id,
                "cursor": cursor,
                "outcome": outcome,
            },
        )


def _stable_id(prefix: str, material: str, length: int) -> str:
    return f"{prefix}{sha256(material.encode('utf-8')).hexdigest()[:length]}"
