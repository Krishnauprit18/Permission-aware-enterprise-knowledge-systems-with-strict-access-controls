"""Ports for local embeddings and disposable OpenSearch derivatives."""

from collections.abc import Sequence
from typing import Protocol

from knowledge_system.domain.embedding import EmbeddingBatch, EmbeddingProvider
from knowledge_system.domain.indexing import SearchIndexDocument


class IndexBackend(Protocol):
    def create_generation(
        self, index_name: str, mapping: dict[str, object]
    ) -> None: ...

    def bulk_index(
        self, index_name: str, documents: Sequence[SearchIndexDocument]
    ) -> None: ...

    def activate_alias(self, index_name: str, alias: str) -> None: ...

    def delete_chunk(self, index_name: str, chunk_id: str) -> None: ...

    def delete_document(self, index_name: str, document_id: str) -> None: ...


__all__ = ["EmbeddingBatch", "EmbeddingProvider", "IndexBackend"]
