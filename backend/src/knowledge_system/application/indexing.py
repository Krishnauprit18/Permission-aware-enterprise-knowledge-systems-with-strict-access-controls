"""Indexing orchestration; no query or authorization decisions live here."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from knowledge_system.application.ports.indexing import IndexBackend
from knowledge_system.domain.content import ContentChunk
from knowledge_system.domain.embedding import ResilientEmbeddingRunner
from knowledge_system.domain.indexing import (
    IndexSchemaConfig,
    build_index_mapping,
    index_document_from_chunk,
)


@dataclass(frozen=True, slots=True)
class IndexingResult:
    index_name: str
    indexed_chunks: int
    embedding_batches: int
    alias: str


@dataclass(frozen=True, slots=True)
class IndexingService:
    backend: IndexBackend
    embeddings: ResilientEmbeddingRunner
    schema: IndexSchemaConfig

    def reindex(
        self, chunks: Sequence[ContentChunk], generation: int
    ) -> IndexingResult:
        index_name = self.schema.index_name(generation)
        self.backend.create_generation(index_name, build_index_mapping(self.schema))
        indexed = 0
        batches = 0
        batch_size = self.embeddings.config.batch_size
        for offset in range(0, len(chunks), batch_size):
            chunk_batch = chunks[offset : offset + batch_size]
            embedding_batches = self.embeddings.embed_many(
                chunk.text for chunk in chunk_batch
            )
            embedding_batch = next(iter(embedding_batches))
            documents = tuple(
                index_document_from_chunk(chunk, embedding_batch, index, self.schema)
                for index, chunk in enumerate(chunk_batch)
            )
            self.backend.bulk_index(index_name, documents)
            indexed += len(documents)
            batches += 1
        self.backend.activate_alias(index_name, self.schema.active_alias)
        return IndexingResult(index_name, indexed, batches, self.schema.active_alias)
