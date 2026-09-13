"""Versioned OpenSearch document contracts and mapping builders."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from knowledge_system.domain.content import ContentChunk
from knowledge_system.domain.embedding import EmbeddingBatch, EmbeddingConfig


class IndexConfigurationMismatch(ValueError):
    """A vector or schema version cannot be mixed into an index generation."""


class IndexDocumentError(ValueError):
    """A chunk cannot become a safe searchable derivative."""


@dataclass(frozen=True, slots=True)
class IndexSchemaConfig:
    schema_version: str = "v1"
    index_prefix: str = "knowledge-chunks"
    active_alias: str = "knowledge-chunks-active"
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"v[0-9]+", self.schema_version):
            raise ValueError("index schema version must look like vN")
        if not re.fullmatch(r"[a-z0-9-]+", self.index_prefix) or not self.active_alias:
            raise ValueError("index names are invalid")

    def index_name(self, generation: int) -> str:
        if generation < 1:
            raise ValueError("index generation must be positive")
        return f"{self.index_prefix}-{self.schema_version}-{generation:06d}"


@dataclass(frozen=True, slots=True)
class SearchIndexDocument:
    document_id: str
    fields: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.document_id.strip() or not self.fields:
            raise IndexDocumentError("index document identity and fields are required")


def build_index_mapping(config: IndexSchemaConfig) -> dict[str, object]:
    """Return an explicit immutable mapping for one schema/vector dimension."""

    return {
        "dynamic": "strict",
        "properties": {
            "chunk_id": {"type": "keyword"},
            "document_id": {"type": "keyword"},
            "document_version_id": {"type": "keyword"},
            "tenant_id": {"type": "keyword"},
            "account_ids": {"type": "keyword"},
            "department": {"type": "keyword"},
            "source_type": {"type": "keyword"},
            "source_external_id": {"type": "keyword"},
            "source_url": {"type": "keyword", "index": False},
            "author": {"type": "keyword"},
            "language": {"type": "keyword"},
            "text": {"type": "text"},
            "content_hash": {"type": "keyword"},
            "classification": {"type": "keyword"},
            "external_shareable": {"type": "boolean"},
            "authority_level": {"type": "integer"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
            "freshness_timestamp": {"type": "date"},
            "status": {"type": "keyword"},
            "acl_relationship_refs": {"type": "keyword"},
            "citation_locators": {"type": "keyword"},
            "ordinal": {"type": "integer"},
            "embedding_model_name": {"type": "keyword"},
            "embedding_model_version": {"type": "keyword"},
            "embedding_dimension": {"type": "integer"},
            "index_schema_version": {"type": "keyword"},
            "vector": {
                "type": "knn_vector",
                "dimension": config.embedding.dimension,
                "method": {
                    "name": "hnsw",
                    "engine": "nmslib",
                    "space_type": "cosinesimil",
                },
            },
        },
    }


def index_document_from_chunk(
    chunk: ContentChunk,
    batch: EmbeddingBatch,
    vector_index: int,
    config: IndexSchemaConfig,
) -> SearchIndexDocument:
    if (
        batch.model_name != config.embedding.model_name
        or batch.model_version != config.embedding.model_version
        or batch.dimension != config.embedding.dimension
        or vector_index >= len(batch.vectors)
    ):
        raise IndexConfigurationMismatch("embedding batch does not match index schema")
    metadata = chunk.metadata
    fields: dict[str, object] = {
        "chunk_id": chunk.chunk_id,
        "document_id": str(chunk.document_id),
        "document_version_id": str(chunk.document_version_id),
        "tenant_id": str(chunk.tenant_id),
        "account_ids": [str(account_id) for account_id in metadata.account_ids],
        "department": metadata.department or "",
        "source_type": metadata.source_type,
        "source_external_id": metadata.source_external_id,
        "source_url": metadata.source_url or "",
        "author": metadata.author or "",
        "language": metadata.language,
        "text": chunk.text,
        "content_hash": chunk.content_hash,
        "classification": metadata.classification.value,
        "external_shareable": metadata.external_shareable,
        "authority_level": metadata.authority_level,
        "created_at": metadata.created_at.isoformat(),
        "updated_at": metadata.updated_at.isoformat(),
        "freshness_timestamp": metadata.updated_at.isoformat(),
        "status": "ACTIVE",
        "acl_relationship_refs": list(metadata.acl_relationship_refs),
        "citation_locators": list(chunk.citation_locators),
        "ordinal": chunk.ordinal,
        "embedding_model_name": batch.model_name,
        "embedding_model_version": batch.model_version,
        "embedding_dimension": batch.dimension,
        "index_schema_version": config.schema_version,
        "vector": list(batch.vectors[vector_index]),
    }
    return SearchIndexDocument(document_id=chunk.chunk_id, fields=fields)
