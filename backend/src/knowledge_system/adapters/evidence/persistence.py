"""PostgreSQL and MinIO evidence store with strict canonical reconstruction checks."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import cast

from psycopg import Connection
from psycopg.rows import dict_row

from knowledge_system.application.content import ContentPipeline
from knowledge_system.application.ports.ingestion import RawObjectReader
from knowledge_system.application.ports.knowledge import EvidenceContentStore
from knowledge_system.domain.content import ContentChunk
from knowledge_system.domain.contracts import AuthorizationOutcome
from knowledge_system.domain.evidence import (
    EvidenceDecisionStatus,
    EvidenceFreshness,
    EvidenceMaterial,
    EvidencePolicyMetadata,
)
from knowledge_system.domain.ingestion import SourceEnvelope
from knowledge_system.domain.persistence import (
    AccountId,
    Classification,
    DocumentId,
    DocumentMetadata,
    LifecycleStatus,
    TenantId,
)
from knowledge_system.domain.retrieval import RetrievalCandidate

ConnectionFactory = Callable[[], Connection[dict[str, object]]]


class EvidenceStoreIntegrityError(RuntimeError):
    """Canonical metadata and raw evidence could not be joined safely."""


@dataclass(frozen=True, slots=True)
class _CanonicalEvidenceRecord:
    candidate: RetrievalCandidate
    metadata: DocumentMetadata
    raw_object_ref: str
    raw_content_hash: str
    chunk_content_hash: str
    ordinal: int
    supersedes_document_ids: tuple[str, ...]
    superseded_by_document_ids: tuple[str, ...]
    lineage: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class PostgresMinioEvidenceContentStore(EvidenceContentStore):
    """Load only active, tenant-bound chunks from canonical metadata and MinIO.

    This adapter is deliberately not an authorization source. P13 rechecks
    OpenFGA before calling it; the adapter then rejects mismatched candidate
    metadata rather than attempting a best-effort lookup.
    """

    connection_factory: ConnectionFactory
    raw_objects: RawObjectReader
    pipeline: ContentPipeline
    max_raw_bytes: int = 2 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.max_raw_bytes < 1:
            raise ValueError("evidence raw byte limit must be positive")

    def load(
        self, candidates: Sequence[RetrievalCandidate]
    ) -> Sequence[EvidenceMaterial]:
        if len({candidate.chunk_id for candidate in candidates}) != len(candidates):
            raise EvidenceStoreIntegrityError("duplicate evidence chunk request")
        records = self._load_records(candidates)
        if len(records) != len(candidates):
            raise EvidenceStoreIntegrityError(
                "canonical evidence record is unavailable"
            )
        return tuple(self._materialize(record) for record in records)

    def _load_records(
        self, candidates: Sequence[RetrievalCandidate]
    ) -> tuple[_CanonicalEvidenceRecord, ...]:
        connection = self.connection_factory()
        try:
            records = tuple(
                self._load_record(connection, candidate) for candidate in candidates
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return records

    def _load_record(
        self,
        connection: Connection[dict[str, object]],
        candidate: RetrievalCandidate,
    ) -> _CanonicalEvidenceRecord:
        if (
            candidate.authorization.outcome is not AuthorizationOutcome.ALLOW
            or not candidate.authorization.allowed
        ):
            raise EvidenceStoreIntegrityError("unauthorized evidence read")
        row = self._fetchone(
            connection,
            """
            SELECT
                c.chunk_id, c.ordinal, c.content_hash AS chunk_content_hash,
                c.status AS chunk_status, c.version_id,
                v.raw_object_ref, v.content_hash AS raw_content_hash,
                v.status AS version_status,
                s.document_id, s.tenant_id, s.source_type, s.source_external_id,
                s.source_url, s.department, s.author, s.classification,
                s.external_shareable, s.authority_level, s.acl_relationship_refs,
                s.version, s.content_hash, s.language, s.status AS source_status,
                s.supersedes_document_id, s.lineage, s.created_at, s.updated_at
            FROM chunks AS c
            JOIN document_versions AS v
                ON v.version_id = c.version_id
                AND v.document_id = c.document_id
                AND v.tenant_id = c.tenant_id
            JOIN source_items AS s
                ON s.document_id = c.document_id AND s.tenant_id = c.tenant_id
            WHERE c.chunk_id = %s AND c.tenant_id = %s
            """,
            (candidate.chunk_id, candidate.tenant_id),
        )
        if row is None:
            raise EvidenceStoreIntegrityError(
                "canonical evidence record is unavailable"
            )
        self._validate_active_row(row)
        accounts = self._fetchall(
            connection,
            """
            SELECT account_id FROM source_item_accounts
            WHERE document_id = %s AND tenant_id = %s ORDER BY account_id
            """,
            (candidate.document_id, candidate.tenant_id),
        )
        metadata = self._metadata(row, accounts)
        self._validate_candidate(candidate, row, metadata)
        document_id = _required_str(row, "document_id")
        tenant_id = _required_str(row, "tenant_id")
        superseded_by = self._fetchall(
            connection,
            """
            SELECT document_id FROM source_items
            WHERE tenant_id = %s AND supersedes_document_id = %s AND status = 'ACTIVE'
            ORDER BY document_id
            """,
            (tenant_id, document_id),
        )
        return _CanonicalEvidenceRecord(
            candidate=candidate,
            metadata=metadata,
            raw_object_ref=_required_str(row, "raw_object_ref"),
            raw_content_hash=_required_str(row, "raw_content_hash"),
            chunk_content_hash=_required_str(row, "chunk_content_hash"),
            ordinal=_required_int(row, "ordinal"),
            supersedes_document_ids=_optional_id_tuple(row, "supersedes_document_id"),
            superseded_by_document_ids=tuple(
                _required_str(value, "document_id") for value in superseded_by
            ),
            lineage=_mapping(row, "lineage"),
        )

    def _materialize(self, record: _CanonicalEvidenceRecord) -> EvidenceMaterial:
        payload = self.raw_objects.get(
            record.raw_object_ref,
            expected_content_hash=record.raw_content_hash,
            max_bytes=self.max_raw_bytes,
        )
        if f"sha256:{sha256(payload).hexdigest()}" != record.metadata.content_hash:
            raise EvidenceStoreIntegrityError("canonical raw content hash mismatch")
        envelope = SourceEnvelope(
            document_id=DocumentId(record.candidate.document_id),
            metadata=record.metadata,
            external_cursor=record.lineage.get(
                "source_cursor", record.candidate.document_version_id
            ),
            raw_content=payload,
            acl_relationships=(),
            is_deleted=False,
            content_type=_content_type(record.metadata.source_type),
            source_path=record.raw_object_ref,
            supersedes_document_id=(
                DocumentId(record.supersedes_document_ids[0])
                if record.supersedes_document_ids
                else None
            ),
        )
        chunks, _metrics = self.pipeline.process(envelope)
        chunk = _select_chunk(chunks, record)
        if chunk.content_hash != record.chunk_content_hash:
            raise EvidenceStoreIntegrityError("canonical chunk hash mismatch")
        return EvidenceMaterial(
            candidate=record.candidate,
            text=chunk.text,
            policy=EvidencePolicyMetadata(
                authority_level=record.metadata.authority_level,
                effective_at=record.metadata.updated_at,
                freshness=(
                    EvidenceFreshness.SUPERSEDED
                    if record.superseded_by_document_ids
                    else EvidenceFreshness.CURRENT
                ),
                decision_status=_decision_status(record.lineage),
                conflict_group=record.lineage.get("evidence_conflict_group"),
                is_current=not record.superseded_by_document_ids,
                supersedes_document_ids=record.supersedes_document_ids,
                superseded_by_document_ids=record.superseded_by_document_ids,
            ),
        )

    @staticmethod
    def _fetchone(
        connection: Connection[dict[str, object]],
        query: str,
        params: tuple[object, ...],
    ) -> Mapping[str, object] | None:
        try:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, params)
                return cast(Mapping[str, object] | None, cursor.fetchone())
        except Exception as exc:
            raise EvidenceStoreIntegrityError("canonical evidence read failed") from exc

    @staticmethod
    def _fetchall(
        connection: Connection[dict[str, object]],
        query: str,
        params: tuple[object, ...],
    ) -> tuple[Mapping[str, object], ...]:
        try:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, params)
                return tuple(
                    cast(Mapping[str, object], row) for row in cursor.fetchall()
                )
        except Exception as exc:
            raise EvidenceStoreIntegrityError("canonical evidence read failed") from exc

    @staticmethod
    def _validate_active_row(row: Mapping[str, object]) -> None:
        if any(
            _required_str(row, field) != LifecycleStatus.ACTIVE.value
            for field in ("source_status", "version_status", "chunk_status")
        ):
            raise EvidenceStoreIntegrityError("inactive evidence cannot be loaded")

    @staticmethod
    def _metadata(
        row: Mapping[str, object], accounts: Sequence[Mapping[str, object]]
    ) -> DocumentMetadata:
        refs = row.get("acl_relationship_refs")
        if not isinstance(refs, list) or any(
            not isinstance(value, str) for value in refs
        ):
            raise EvidenceStoreIntegrityError("canonical ACL references are invalid")
        return DocumentMetadata(
            source_type=_required_str(row, "source_type"),
            source_external_id=_required_str(row, "source_external_id"),
            source_url=_optional_str(row, "source_url"),
            tenant_id=TenantId(_required_str(row, "tenant_id")),
            account_ids=tuple(
                AccountId(_required_str(account, "account_id")) for account in accounts
            ),
            department=_optional_str(row, "department"),
            created_at=_required_datetime(row, "created_at"),
            updated_at=_required_datetime(row, "updated_at"),
            author=_optional_str(row, "author"),
            classification=Classification(_required_str(row, "classification")),
            external_shareable=_required_bool(row, "external_shareable"),
            authority_level=_required_int(row, "authority_level"),
            acl_relationship_refs=tuple(refs),
            version=_required_int(row, "version"),
            content_hash=_required_str(row, "content_hash"),
            language=_required_str(row, "language"),
        )

    @staticmethod
    def _validate_candidate(
        candidate: RetrievalCandidate,
        row: Mapping[str, object],
        metadata: DocumentMetadata,
    ) -> None:
        if (
            candidate.tenant_id != str(metadata.tenant_id)
            or candidate.document_id != _required_str(row, "document_id")
            or candidate.document_version_id != _required_str(row, "version_id")
            or candidate.source_type != metadata.source_type
            or candidate.source_external_id != metadata.source_external_id
            or candidate.classification != metadata.classification.value
            or tuple(sorted(candidate.account_ids))
            != tuple(sorted(map(str, metadata.account_ids)))
            or candidate.department != (metadata.department or "")
            or candidate.updated_at.astimezone(UTC) != metadata.updated_at
            or candidate.external_shareable != metadata.external_shareable
        ):
            raise EvidenceStoreIntegrityError(
                "candidate metadata does not match canonical evidence"
            )


def _select_chunk(
    chunks: Sequence[ContentChunk], record: _CanonicalEvidenceRecord
) -> ContentChunk:
    matches = [
        chunk
        for chunk in chunks
        if chunk.chunk_id == record.candidate.chunk_id
        and chunk.ordinal == record.ordinal
    ]
    if len(matches) != 1:
        raise EvidenceStoreIntegrityError("canonical chunk cannot be reconstructed")
    chunk = matches[0]
    if tuple(chunk.citation_locators) != record.candidate.citation_locators:
        raise EvidenceStoreIntegrityError(
            "candidate citation locators do not match canonical evidence"
        )
    return chunk


def _content_type(source_type: str) -> str:
    if source_type in {"document", "policy", "contract"}:
        return "text/markdown"
    if source_type in {
        "support_ticket",
        "slack_thread",
        "call_transcript",
        "hourly_feed",
    }:
        return "application/json"
    raise EvidenceStoreIntegrityError("canonical source type is unsupported")


def _decision_status(lineage: Mapping[str, str]) -> EvidenceDecisionStatus:
    raw_status = lineage.get("evidence_decision_status", "INFORMATIONAL")
    try:
        return EvidenceDecisionStatus(raw_status.upper())
    except ValueError as exc:
        raise EvidenceStoreIntegrityError(
            "canonical evidence decision status is invalid"
        ) from exc


def _required_str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceStoreIntegrityError("canonical evidence field is invalid")
    return value


def _optional_str(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is not None and not isinstance(value, str):
        raise EvidenceStoreIntegrityError("canonical evidence field is invalid")
    return value


def _required_int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, int):
        raise EvidenceStoreIntegrityError("canonical evidence field is invalid")
    return value


def _required_bool(row: Mapping[str, object], key: str) -> bool:
    value = row.get(key)
    if not isinstance(value, bool):
        raise EvidenceStoreIntegrityError("canonical evidence field is invalid")
    return value


def _required_datetime(row: Mapping[str, object], key: str) -> datetime:
    value = row.get(key)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise EvidenceStoreIntegrityError("canonical evidence timestamp is invalid")
    return value.astimezone(UTC)


def _mapping(row: Mapping[str, object], key: str) -> Mapping[str, str]:
    value = row.get(key)
    if not isinstance(value, dict) or any(
        not isinstance(item_key, str) or not isinstance(item_value, str)
        for item_key, item_value in value.items()
    ):
        raise EvidenceStoreIntegrityError("canonical evidence lineage is invalid")
    return dict(value)


def _optional_id_tuple(row: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = row.get(key)
    if value is None:
        return ()
    if not isinstance(value, str) or not value.strip():
        raise EvidenceStoreIntegrityError("canonical evidence lineage is invalid")
    return (value,)
