"""Live P11 OpenSearch evidence; opt in with P11_OPENSEARCH_LIVE=1."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from knowledge_system.adapters.search.opensearch import (
    HttpxOpenSearchTransport,
    OpenSearchAdapterError,
    OpenSearchConfig,
    OpenSearchIndexAdapter,
)
from knowledge_system.application.indexing import IndexingService
from knowledge_system.domain.content import (
    ContentChunk,
    SourceLocator,
    build_content_chunk,
)
from knowledge_system.domain.embedding import (
    EmbeddingConfig,
    LocalSemanticEmbeddingProvider,
    ResilientEmbeddingRunner,
)
from knowledge_system.domain.indexing import IndexSchemaConfig
from knowledge_system.domain.persistence import (
    AccountId,
    Classification,
    DocumentId,
    DocumentMetadata,
    DocumentVersionId,
    TenantId,
)

pytestmark = pytest.mark.integration


def _load_env() -> None:
    path = Path(os.environ.get("PLATFORM_ENV_FILE", ".env.local"))
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        path = Path(__file__).resolve().parents[3] / ".env.local"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key, value)


def _chunk(document_id: str, text: str, ordinal: int) -> ContentChunk:
    now = datetime(2026, 9, 13, tzinfo=UTC)
    metadata = DocumentMetadata(
        source_type="document",
        source_external_id=document_id,
        source_url=None,
        tenant_id=TenantId("northstar"),
        account_ids=(AccountId("acme"),),
        department="product",
        created_at=now,
        updated_at=now,
        author="Synthetic Author",
        classification=Classification.INTERNAL,
        external_shareable=False,
        authority_level=4,
        acl_relationship_refs=(f"resource:{document_id}#viewer",),
        version=1,
        content_hash=f"sha256:{document_id}",
        language="en",
    )
    return build_content_chunk(
        DocumentId(document_id),
        DocumentVersionId(f"{document_id}:v1"),
        metadata,
        ordinal,
        text,
        (SourceLocator("document", document_id, section_path=("Evidence",)),),
    )


def _live_context() -> tuple[
    OpenSearchIndexAdapter,
    IndexingService,
    IndexSchemaConfig,
    tuple[ContentChunk, ...],
    HttpxOpenSearchTransport,
]:
    _load_env()
    if os.environ.get("P11_OPENSEARCH_LIVE") != "1":
        pytest.skip("set P11_OPENSEARCH_LIVE=1 for live OpenSearch evidence")
    model_path = os.environ.get("EMBEDDING_MODEL_PATH", "")
    if not model_path:
        pytest.skip("EMBEDDING_MODEL_PATH is required for live semantic evidence")
    config = EmbeddingConfig(
        model_name=os.environ.get("EMBEDDING_MODEL_NAME", "BAAI/bge-small-en-v1.5"),
        model_version=os.environ.get("EMBEDDING_MODEL_VERSION", "2026-09"),
        dimension=int(os.environ.get("EMBEDDING_DIMENSION", "384")),
        batch_size=2,
    )
    suffix = uuid4().hex[:10]
    schema = IndexSchemaConfig(
        index_prefix=f"p11-live-{suffix}",
        active_alias=f"p11-live-active-{suffix}",
        embedding=config,
    )
    transport = HttpxOpenSearchTransport(
        OpenSearchConfig(
            endpoint=os.environ.get("OPENSEARCH_URL", "https://127.0.0.1:9200"),
            username=os.environ.get("OPENSEARCH_USERNAME", "admin"),
            password=os.environ.get("OPENSEARCH_INITIAL_ADMIN_PASSWORD", ""),
        )
    )
    adapter = OpenSearchIndexAdapter(transport)
    service = IndexingService(
        adapter,
        ResilientEmbeddingRunner(
            LocalSemanticEmbeddingProvider(model_path, config), config
        ),
        schema,
    )
    chunks = (
        _chunk(
            "live-approved-launch",
            "Acme Retail approved launch date is September 18 2026.",
            0,
        ),
        _chunk(
            "live-support-window",
            "Acme Retail support coverage begins at 09:00 UTC for the launch.",
            1,
        ),
    )
    return adapter, service, schema, chunks, transport


def _mapping_body(response_body: Mapping[str, object]) -> Mapping[str, object]:
    assert len(response_body) == 1
    return cast(Mapping[str, object], next(iter(response_body.values())))


@pytest.mark.security
def test_live_opensearch_mapping_bm25_and_ann_queries() -> None:
    adapter, service, schema, chunks, transport = _live_context()
    index_name = schema.index_name(1)
    created = False
    try:
        result = service.reindex(chunks, 1)
        created = True
        assert result.index_name == index_name

        definition = _mapping_body(transport.request("GET", f"/{index_name}").body)
        mappings = cast(Mapping[str, object], definition["mappings"])
        properties = cast(Mapping[str, object], mappings["properties"])
        vector = cast(Mapping[str, object], properties["vector"])
        settings = cast(Mapping[str, object], definition["settings"])
        index_settings = cast(Mapping[str, object], settings["index"])
        assert vector["dimension"] == 384
        assert str(index_settings["knn"]).lower() == "true"

        query_vector = service.embeddings.provider.embed_batch(
            ("approved launch date for Acme Retail",)
        ).vectors[0]
        ann = adapter.search_knn(index_name, query_vector, 1).body
        ann_hits = cast(list[object], cast(Mapping[str, object], ann["hits"])["hits"])
        assert cast(Mapping[str, object], ann_hits[0])["_id"] == chunks[0].chunk_id

        bm25 = adapter.search_bm25(index_name, "September 18 2026", 1).body
        bm25_hits = cast(list[object], cast(Mapping[str, object], bm25["hits"])["hits"])
        assert cast(Mapping[str, object], bm25_hits[0])["_id"] == chunks[0].chunk_id
    finally:
        if created:
            try:
                adapter.delete_generation(index_name)
            except OpenSearchAdapterError:
                pytest.fail("live index cleanup failed")


@pytest.mark.security
def test_live_opensearch_alias_cutover_and_deletion() -> None:
    adapter, service, schema, chunks, transport = _live_context()
    first = schema.index_name(1)
    second = schema.index_name(2)
    created: set[str] = set()
    try:
        service.reindex(chunks, 1)
        created.add(first)
        service.reindex(chunks, 2)
        created.add(second)
        alias = transport.request("GET", f"/_alias/{schema.active_alias}")
        assert alias.status_code == 200
        assert set(alias.body) == {second}

        adapter.delete_chunk(second, chunks[0].chunk_id)
        remaining = adapter.search_bm25(second, "September 18 2026", 10).body
        remaining_hits = cast(
            list[object], cast(Mapping[str, object], remaining["hits"])["hits"]
        )
        assert all(
            cast(Mapping[str, object], hit)["_id"] != chunks[0].chunk_id
            for hit in remaining_hits
        )
    finally:
        for index_name in created:
            try:
                adapter.delete_generation(index_name)
            except OpenSearchAdapterError:
                pytest.fail("live index cleanup failed")
