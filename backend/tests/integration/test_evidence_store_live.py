"""Opt-in PostgreSQL plus MinIO proof for the production evidence-content store."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import psycopg
import pytest
from psycopg import Connection
from psycopg.sql import SQL, Identifier

from knowledge_system.adapters.content.parsers import FixtureContentParser
from knowledge_system.adapters.evidence.persistence import (
    EvidenceStoreIntegrityError,
    PostgresMinioEvidenceContentStore,
)
from knowledge_system.adapters.object_store.minio import MinioRawObjectStore
from knowledge_system.adapters.persistence.postgres import PostgresUnitOfWork
from knowledge_system.application.content import (
    BoundedContentChunker,
    ContentPipeline,
    SafeContentNormalizer,
)
from knowledge_system.domain.content import ChunkingLimits
from knowledge_system.domain.contracts import (
    AuthorizationDecision,
    AuthorizationOutcome,
    AuthorizedObjectId,
)
from knowledge_system.domain.ingestion import RawObjectKey, RawSnapshot, SourceEnvelope
from knowledge_system.domain.persistence import (
    Account,
    AccountId,
    ChunkId,
    ChunkMetadata,
    Classification,
    DocumentId,
    DocumentMetadata,
    DocumentVersion,
    DocumentVersionId,
    SourceConnection,
    SourceConnectionId,
    SourceItem,
    Tenant,
    TenantId,
)
from knowledge_system.domain.retrieval import RetrievalCandidate

ROOT = Path(__file__).parents[3]
MIGRATION = ROOT / "backend" / "migrations" / "0001_initial.sql"
DatabaseFactory = Callable[[], Connection[dict[str, object]]]

pytestmark = [pytest.mark.integration, pytest.mark.security]


def _load_env() -> dict[str, str]:
    path = Path(os.environ.get("PLATFORM_ENV_FILE", ROOT / ".env.local"))
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    return values


def _database_url(values: dict[str, str]) -> str | None:
    configured = os.environ.get("DATABASE_URL")
    if configured:
        return configured
    user = values.get("POSTGRES_USER")
    password = values.get("POSTGRES_PASSWORD")
    database = values.get("POSTGRES_DB")
    if not user or not password or not database:
        return None
    host = os.environ.get("P13_EVIDENCE_DATABASE_HOST", "localhost")
    return (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:5432/{quote(database, safe='')}"
    )


def _factory(url: str, schema: str) -> DatabaseFactory:
    def connect() -> Connection[dict[str, object]]:
        connection = psycopg.connect(url, row_factory=psycopg.rows.dict_row)
        connection.execute(SQL("SET search_path TO {} ").format(Identifier(schema)))
        return connection

    return connect


def test_live_canonical_evidence_store_reconstructs_only_verified_active_chunk() -> (
    None
):
    if os.environ.get("P13_EVIDENCE_STORE_LIVE") != "1":
        pytest.skip("set P13_EVIDENCE_STORE_LIVE=1 for PostgreSQL/MinIO evidence")
    values = _load_env()
    database_url = _database_url(values)
    endpoint = os.environ.get("P13_EVIDENCE_MINIO_ENDPOINT", "")
    access_key = values.get("MINIO_ROOT_USER")
    secret_key = values.get("MINIO_ROOT_PASSWORD")
    if not database_url or not endpoint or not access_key or not secret_key:
        pytest.skip("local PostgreSQL/MinIO evidence configuration is unavailable")

    try:
        root_connection = psycopg.connect(database_url)
    except psycopg.Error as exc:
        pytest.skip(f"PostgreSQL is unavailable: {type(exc).__name__}")
    schema = f"p13_evidence_{uuid4().hex}"
    raw_key = f"p13-evidence/{uuid4().hex}/primary.bin"
    raw_store = MinioRawObjectStore(
        endpoint, access_key, secret_key, bucket="raw", secure=False
    )
    try:
        with root_connection.transaction():
            root_connection.execute(SQL("CREATE SCHEMA {}").format(Identifier(schema)))
            root_connection.execute(
                SQL("SET search_path TO {}").format(Identifier(schema))
            )
            root_connection.execute(MIGRATION.read_text(encoding="utf-8"))
        factory = _factory(database_url, schema)
        now = datetime(2026, 9, 14, tzinfo=UTC)
        tenant = Tenant(TenantId("northstar"), "Northstar", now, now)
        account = Account(
            AccountId("acme"), tenant.tenant_id, "acme", "Acme Retail", now, now
        )
        connection = SourceConnection(
            SourceConnectionId("conn-evidence"),
            tenant.tenant_id,
            "document",
            "evidence-fixture",
            None,
            None,
            now,
            now,
        )
        payload = b"# Release board\n\nThe release board approved Acme rollout for September 24.\n"
        digest = f"sha256:{sha256(payload).hexdigest()}"
        metadata = DocumentMetadata(
            source_type="document",
            source_external_id="evidence-release-board",
            source_url="https://docs.northstar.invalid/evidence-release-board",
            tenant_id=tenant.tenant_id,
            account_ids=(account.account_id,),
            department="product",
            created_at=now,
            updated_at=now,
            author="priya-product-manager",
            classification=Classification.INTERNAL,
            external_shareable=False,
            authority_level=5,
            acl_relationship_refs=("resource:doc-evidence#can_view",),
            version=1,
            content_hash=digest,
            language="en",
        )
        pipeline = ContentPipeline(
            parser=FixtureContentParser(ChunkingLimits()),
            normalizer=SafeContentNormalizer(ChunkingLimits()),
            chunker=BoundedContentChunker(ChunkingLimits()),
        )
        envelope = SourceEnvelope(
            document_id=DocumentId("doc-evidence"),
            metadata=metadata,
            external_cursor="cursor-1",
            raw_content=payload,
            acl_relationships=(),
            is_deleted=False,
            content_type="text/markdown",
        )
        content_chunks, _metrics = pipeline.process(envelope)
        content_chunk = content_chunks[0]
        raw_reference = raw_store.put(
            RawSnapshot(
                object_key=RawObjectKey(raw_key),
                payload=payload,
                content_type="text/markdown",
                metadata={"source-content-hash": digest},
            )
        )
        item = SourceItem(
            DocumentId("doc-evidence"),
            connection.connection_id,
            metadata,
            lineage={"source_cursor": "cursor-1"},
        )
        version = DocumentVersion(
            DocumentVersionId("doc-evidence-v1"),
            item.document_id,
            1,
            digest,
            raw_reference.object_uri,
            now,
        )
        chunk = ChunkMetadata(
            ChunkId(content_chunk.chunk_id),
            item.document_id,
            version.version_id,
            tenant.tenant_id,
            content_chunk.ordinal,
            content_chunk.content_hash,
            "search://doc-evidence/chunk-0",
            "embedding-v1",
            "index-v1",
            now,
        )
        with PostgresUnitOfWork(factory) as repository:
            repository.save_tenant(tenant)
            repository.save_account(account)
            repository.save_source_connection(connection)
            repository.save_source_item(item)
            repository.append_document_version(version)
            repository.save_chunk_metadata(chunk)

        candidate = RetrievalCandidate(
            chunk_id=content_chunk.chunk_id,
            resource_id=AuthorizedObjectId("resource:doc-evidence"),
            tenant_id="northstar",
            source_type="document",
            source_external_id=metadata.source_external_id,
            document_id="doc-evidence",
            document_version_id="doc-evidence-v1",
            classification=Classification.INTERNAL.value,
            account_ids=("acme",),
            department="product",
            citation_locators=content_chunk.citation_locators,
            updated_at=now,
            authorization=AuthorizationDecision(
                allowed=True,
                outcome=AuthorizationOutcome.ALLOW,
                decision_fingerprint="e" * 64,
                authorization_model_id="model-p13r",
                tuple_version="tuple-p13r",
                policy_version="policy-p13r",
            ),
            external_shareable=False,
        )
        store = PostgresMinioEvidenceContentStore(factory, raw_store, pipeline)

        material = store.load((candidate,))[0]

        assert material.text == content_chunk.text
        assert material.policy.authority_level == 5
        assert material.policy.freshness.value == "CURRENT"
        with pytest.raises(EvidenceStoreIntegrityError, match="citation locators"):
            store.load((replace(candidate, citation_locators=("wrong",)),))
    finally:
        try:
            raw_store._client.remove_object("raw", raw_key)
        finally:
            root_connection.execute("SET search_path TO public")
            root_connection.execute(
                SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(Identifier(schema))
            )
            root_connection.commit()
            root_connection.close()
