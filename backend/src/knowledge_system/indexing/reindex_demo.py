"""Build the synthetic local index through the P09/P10 boundaries."""

from __future__ import annotations

import os
from pathlib import Path

from knowledge_system.adapters.connectors.fixtures import (
    CallTranscriptFixtureConnector,
    FilesystemFixtureConnector,
    SlackFixtureConnector,
    SupportTicketFixtureConnector,
)
from knowledge_system.adapters.content.parsers import FixtureContentParser
from knowledge_system.adapters.search.opensearch import (
    HttpxOpenSearchTransport,
    OpenSearchConfig,
    OpenSearchIndexAdapter,
)
from knowledge_system.application.content import (
    BoundedContentChunker,
    ContentPipeline,
    SafeContentNormalizer,
)
from knowledge_system.application.indexing import IndexingService
from knowledge_system.domain.content import ContentChunk
from knowledge_system.domain.embedding import (
    EmbeddingConfig,
    LocalSemanticEmbeddingProvider,
    ResilientEmbeddingRunner,
)
from knowledge_system.domain.indexing import IndexSchemaConfig
from knowledge_system.domain.ingestion import SourceEnvelope


def _load_local_env() -> None:
    path = Path(os.environ.get("PLATFORM_ENV_FILE", ".env.local"))
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        path = Path(__file__).resolve().parents[4] / ".env.local"
    if not path.is_file():
        raise RuntimeError(".env.local is required; run make bootstrap-platform first")
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key, value)


def _collect_chunks(dataset_root: Path) -> tuple[ContentChunk, ...]:
    pipeline = ContentPipeline(
        FixtureContentParser(), SafeContentNormalizer(), BoundedContentChunker()
    )
    connectors = (
        FilesystemFixtureConnector(dataset_root),
        SupportTicketFixtureConnector(dataset_root),
        SlackFixtureConnector(dataset_root),
        CallTranscriptFixtureConnector(dataset_root),
    )
    chunks: list[ContentChunk] = []
    for connector in connectors:
        for result in connector.iter_changes(None):
            if isinstance(result, SourceEnvelope) and not result.is_deleted:
                indexed, _metrics = pipeline.process(result)
                chunks.extend(indexed)
    return tuple(chunks)


def main() -> None:
    _load_local_env()
    root = Path(__file__).resolve().parents[4]
    embedding = EmbeddingConfig(
        model_name=os.environ.get("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2"),
        model_version=os.environ.get("EMBEDDING_MODEL_VERSION", "1"),
        dimension=int(os.environ.get("EMBEDDING_DIMENSION", "384")),
        batch_size=int(os.environ.get("EMBEDDING_BATCH_SIZE", "16")),
    )
    model_path = os.environ.get("EMBEDDING_MODEL_PATH", "")
    if not model_path:
        raise RuntimeError("EMBEDDING_MODEL_PATH is required for semantic reindexing")
    schema = IndexSchemaConfig(embedding=embedding)
    transport = HttpxOpenSearchTransport(
        OpenSearchConfig(
            endpoint=os.environ.get("OPENSEARCH_URL", "https://127.0.0.1:9200"),
            username=os.environ.get("OPENSEARCH_USERNAME", "admin"),
            password=os.environ.get("OPENSEARCH_INITIAL_ADMIN_PASSWORD", ""),
        )
    )
    service = IndexingService(
        OpenSearchIndexAdapter(transport),
        ResilientEmbeddingRunner(
            LocalSemanticEmbeddingProvider(model_path, embedding), embedding
        ),
        schema,
    )
    chunks = _collect_chunks(root / "data" / "synthetic")
    result = service.reindex(chunks, int(os.environ.get("INDEX_GENERATION", "1")))
    print(
        f"Indexed {result.indexed_chunks} chunks in {result.index_name}; "
        f"embedding_batches={result.embedding_batches}; alias={result.alias}"
    )


if __name__ == "__main__":
    main()
