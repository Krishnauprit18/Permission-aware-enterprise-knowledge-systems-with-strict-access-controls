"""P11 regression tests for local embeddings and disposable OpenSearch indexes."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from knowledge_system.adapters.connectors.fixtures import FilesystemFixtureConnector
from knowledge_system.adapters.content.parsers import FixtureContentParser
from knowledge_system.adapters.search.opensearch import (
    OpenSearchAdapterError,
    OpenSearchConfig,
    OpenSearchIndexAdapter,
    OpenSearchResponse,
    OpenSearchTransport,
)
from knowledge_system.application.content import (
    BoundedContentChunker,
    ContentPipeline,
    SafeContentNormalizer,
)
from knowledge_system.application.indexing import IndexingService
from knowledge_system.domain.content import (
    ContentChunk,
    SourceLocator,
    build_content_chunk,
)
from knowledge_system.domain.embedding import (
    EmbeddingBatch,
    EmbeddingConfig,
    EmbeddingError,
    EmbeddingInputError,
    EmbeddingVersionMismatch,
    LocalHashEmbeddingProvider,
    ResilientEmbeddingRunner,
)
from knowledge_system.domain.indexing import (
    IndexConfigurationMismatch,
    IndexDocumentError,
    IndexSchemaConfig,
    SearchIndexDocument,
    build_index_mapping,
    index_document_from_chunk,
)
from knowledge_system.domain.ingestion import SourceEnvelope
from knowledge_system.domain.persistence import (
    AccountId,
    Classification,
    DocumentId,
    DocumentMetadata,
    DocumentVersionId,
    TenantId,
)

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 9, 13, 6, 0, tzinfo=UTC)


def _metadata(
    *, classification: Classification = Classification.INTERNAL
) -> DocumentMetadata:
    return DocumentMetadata(
        source_type="document",
        source_external_id="fixture-doc",
        source_url=None,
        tenant_id=TenantId("northstar"),
        account_ids=(AccountId("acme"),),
        department="product",
        created_at=NOW,
        updated_at=NOW,
        author="Synthetic Author",
        classification=classification,
        external_shareable=False,
        authority_level=3,
        acl_relationship_refs=("resource:fixture-doc#viewer",),
        version=1,
        content_hash="sha256:fixture",
        language="en",
    )


def _chunk(*, classification: Classification = Classification.INTERNAL) -> ContentChunk:
    metadata = _metadata(classification=classification)
    return build_content_chunk(
        DocumentId("fixture-doc"),
        DocumentVersionId("fixture-doc:v1"),
        metadata,
        0,
        "Approved synthetic rollout evidence.",
        (SourceLocator("document", "fixture-doc", section_path=("Evidence",)),),
    )


@pytest.mark.unit
def test_local_embedding_is_deterministic_and_versioned() -> None:
    config = EmbeddingConfig(dimension=16, batch_size=2)
    provider = LocalHashEmbeddingProvider(config)
    first = provider.embed_batch(("Acme rollout",))
    second = provider.embed_batch(("Acme rollout",))

    assert first == second
    assert first.model_name == "local-hash-embedding"
    assert first.model_version == "1"
    assert len(first.vectors[0]) == 16
    assert (
        pytest.approx(sum(value * value for value in first.vectors[0]), abs=1e-6) == 1.0
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "kwargs",
    [
        {"model_name": ""},
        {"model_version": ""},
        {"dimension": 1},
        {"batch_size": 0},
        {"max_text_chars": 0},
        {"timeout_seconds": 0},
        {"max_retries": -1},
        {"retry_base_seconds": -1},
    ],
)
def test_embedding_config_rejects_invalid_bounds(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        EmbeddingConfig(**kwargs)  # type: ignore[arg-type]


@pytest.mark.unit
def test_embedding_batch_and_text_validation_are_fail_closed() -> None:
    with pytest.raises(ValueError, match="identity"):
        EmbeddingBatch("", "1", 8, ())
    with pytest.raises(ValueError, match="dimension"):
        EmbeddingBatch("local", "1", 8, ((0.0,) * 7,))
    provider = LocalHashEmbeddingProvider(EmbeddingConfig(max_text_chars=3))
    with pytest.raises(EmbeddingInputError, match="empty or exceeds"):
        provider.embed_batch(("",))
    with pytest.raises(EmbeddingInputError, match="empty or exceeds"):
        provider.embed_batch(("long",))
    assert (
        tuple(ResilientEmbeddingRunner(provider, provider.config).embed_many(())) == ()
    )


@pytest.mark.unit
def test_embedding_runner_bounds_batches_and_retries_transient_provider() -> None:
    @dataclass
    class FlakyProvider:
        calls: int = 0

        def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch:
            self.calls += 1
            if self.calls == 1:
                raise OSError("transient")
            return LocalHashEmbeddingProvider(
                EmbeddingConfig(dimension=8, batch_size=2)
            ).embed_batch(texts)

    config = EmbeddingConfig(dimension=8, batch_size=2, max_retries=1)
    provider = FlakyProvider()
    delays: list[float] = []
    batches = tuple(
        ResilientEmbeddingRunner(provider, config, delays.append).embed_many(
            ["one", "two", "three"]
        )
    )

    assert [len(batch.vectors) for batch in batches] == [2, 1]
    assert provider.calls == 3
    assert delays


@pytest.mark.unit
def test_embedding_timeout_and_input_bounds_fail_clearly() -> None:
    @dataclass
    class SlowProvider:
        def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch:
            del texts
            time.sleep(0.05)
            return EmbeddingBatch("local", "1", 8, ((0.0,) * 8,))

    config = EmbeddingConfig(
        model_name="local", dimension=8, timeout_seconds=0.001, max_retries=0
    )
    with pytest.raises(RuntimeError, match="timed out"):
        tuple(ResilientEmbeddingRunner(SlowProvider(), config).embed_many(["text"]))

    with pytest.raises(EmbeddingInputError, match="exceeds"):
        LocalHashEmbeddingProvider(EmbeddingConfig(batch_size=1)).embed_batch(
            ("a", "b")
        )


@pytest.mark.unit
def test_exhausted_provider_retry_is_explicit() -> None:
    @dataclass
    class BrokenProvider:
        def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch:
            del texts
            raise EmbeddingError("broken")

    with pytest.raises(RuntimeError, match="unavailable"):
        tuple(
            ResilientEmbeddingRunner(
                BrokenProvider(),
                EmbeddingConfig(dimension=8, max_retries=1),
                lambda _delay: None,
            ).embed_many(["text"])
        )


@pytest.mark.unit
def test_mapping_is_explicit_and_restricted_document_retains_filter_metadata() -> None:
    config = IndexSchemaConfig(embedding=EmbeddingConfig(dimension=12))
    mapping = build_index_mapping(config)
    properties = cast(dict[str, object], mapping["properties"])
    assert mapping["dynamic"] == "strict"
    assert properties["text"] == {"type": "text"}
    vector_mapping = cast(dict[str, object], properties["vector"])
    assert vector_mapping["dimension"] == 12

    document = index_document_from_chunk(
        _chunk(classification=Classification.RESTRICTED),
        LocalHashEmbeddingProvider(config.embedding).embed_batch(("restricted",)),
        0,
        config,
    )
    assert document.fields["classification"] == "RESTRICTED"
    assert document.fields["tenant_id"] == "northstar"
    assert document.fields["account_ids"] == ["acme"]
    assert document.fields["acl_relationship_refs"] == ["resource:fixture-doc#viewer"]
    assert document.fields["embedding_model_version"] == "1"


@pytest.mark.unit
def test_known_fixture_reindexes_with_deterministic_metadata_and_alias_cutover() -> (
    None
):
    dataset = ROOT / "data" / "synthetic"
    envelope = next(
        item
        for item in FilesystemFixtureConnector(dataset).iter_changes(None)
        if isinstance(item, SourceEnvelope)
        and str(item.document_id) == "doc-acme-approved-launch-date-v3"
    )
    pipeline = ContentPipeline(
        FixtureContentParser(), SafeContentNormalizer(), BoundedContentChunker()
    )
    chunks, _metrics = pipeline.process(envelope)
    backend = FakeBackend()
    config = EmbeddingConfig(dimension=16, batch_size=2)
    result = IndexingService(
        backend,
        ResilientEmbeddingRunner(LocalHashEmbeddingProvider(config), config),
        IndexSchemaConfig(embedding=config),
    ).reindex(chunks, 1)

    assert result.index_name == "knowledge-chunks-v1-000001"
    assert result.indexed_chunks == len(chunks)
    assert result.embedding_batches >= 1
    assert backend.aliases == [(result.index_name, "knowledge-chunks-active")]
    assert backend.documents
    version_id = cast(str, backend.documents[0].fields["document_version_id"])
    assert version_id.endswith(":v3")


@pytest.mark.unit
def test_reindex_rejects_embedding_version_mismatch() -> None:
    config = IndexSchemaConfig(embedding=EmbeddingConfig(dimension=8))
    batch = EmbeddingBatch("other-model", "1", 8, ((0.0,) * 8,))
    with pytest.raises(IndexConfigurationMismatch, match="does not match"):
        index_document_from_chunk(_chunk(), batch, 0, config)

    with pytest.raises(EmbeddingVersionMismatch, match="incompatible"):
        tuple(
            ResilientEmbeddingRunner(
                WrongVersionProvider(),
                EmbeddingConfig(dimension=8, max_retries=0),
            ).embed_many(["text"])
        )

    with pytest.raises(ValueError, match="schema version"):
        IndexSchemaConfig(schema_version="schema-v1")
    with pytest.raises(ValueError, match="index names"):
        IndexSchemaConfig(index_prefix="Unsafe_Name")
    with pytest.raises(ValueError, match="generation"):
        config.index_name(0)
    with pytest.raises(IndexDocumentError, match="identity"):
        SearchIndexDocument("", {})
    with pytest.raises(ValueError, match="document ID"):
        OpenSearchIndexAdapter(FakeTransport()).delete_chunk(
            "knowledge-chunks-v1-000001", "bad/id"
        )


@pytest.mark.unit
def test_opensearch_adapter_creates_bulk_alias_and_deletes_without_leaking_body() -> (
    None
):
    transport = FakeTransport()
    adapter = OpenSearchIndexAdapter(transport)
    adapter.create_generation("knowledge-chunks-v1-000001", {"dynamic": "strict"})
    adapter.bulk_index(
        "knowledge-chunks-v1-000001",
        (
            index_document_from_chunk(
                _chunk(),
                LocalHashEmbeddingProvider(EmbeddingConfig(dimension=8)).embed_batch(
                    ("text",)
                ),
                0,
                IndexSchemaConfig(embedding=EmbeddingConfig(dimension=8)),
            ),
        ),
    )
    adapter.activate_alias("knowledge-chunks-v1-000001", "knowledge-chunks-active")
    adapter.delete_chunk("knowledge-chunks-v1-000001", "chunk_abc")
    adapter.delete_document("knowledge-chunks-v1-000001", "fixture-doc")

    assert [request[0:2] for request in transport.requests] == [
        ("PUT", "/knowledge-chunks-v1-000001"),
        ("POST", "/_bulk"),
        ("POST", "/_aliases"),
        ("DELETE", "/knowledge-chunks-v1-000001/_doc/chunk_abc"),
        ("POST", "/knowledge-chunks-v1-000001/_delete_by_query"),
    ]
    assert "Approved synthetic rollout evidence" in (transport.requests[1][2] or "")
    assert "password" not in str(transport.requests[1][2]).lower()


@pytest.mark.unit
def test_opensearch_endpoint_must_be_local_or_private_and_errors_are_redacted() -> None:
    with pytest.raises(ValueError, match="localhost/private"):
        OpenSearchConfig(endpoint="https://search.example.com")
    assert OpenSearchConfig(endpoint="https://10.0.0.5:9200").endpoint.startswith(
        "https://10."
    )

    transport = FakeTransport(status=500, body={"error": "secret response body"})
    with pytest.raises(OpenSearchAdapterError, match="status 500") as error:
        OpenSearchIndexAdapter(transport).create_generation(
            "knowledge-chunks-v1-000001", {}
        )
    assert "secret response body" not in str(error.value)


@dataclass
class FakeBackend:
    created: list[tuple[str, dict[str, object]]] = field(default_factory=list)
    documents: list[SearchIndexDocument] = field(default_factory=list)
    aliases: list[tuple[str, str]] = field(default_factory=list)

    def create_generation(self, index_name: str, mapping: dict[str, object]) -> None:
        self.created.append((index_name, mapping))

    def bulk_index(
        self, index_name: str, documents: Sequence[SearchIndexDocument]
    ) -> None:
        del index_name
        self.documents.extend(documents)

    def activate_alias(self, index_name: str, alias: str) -> None:
        self.aliases.append((index_name, alias))

    def delete_chunk(self, index_name: str, chunk_id: str) -> None:
        del index_name, chunk_id

    def delete_document(self, index_name: str, document_id: str) -> None:
        del index_name, document_id


@dataclass
class WrongVersionProvider:
    def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch:
        return EmbeddingBatch("other-model", "1", 8, tuple((0.0,) * 8 for _ in texts))


@dataclass
class FakeTransport(OpenSearchTransport):
    status: int = 200
    body: dict[str, object] = field(default_factory=dict)
    requests: list[tuple[str, str, str | None]] = field(default_factory=list)

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: object | None = None,
        raw_body: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> OpenSearchResponse:
        del headers, json_body
        self.requests.append((method, path, raw_body))
        return OpenSearchResponse(self.status, self.body)
