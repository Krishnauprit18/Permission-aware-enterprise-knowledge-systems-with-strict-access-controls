"""Ports for the pre-index content pipeline."""

from typing import Protocol

from knowledge_system.domain.content import (
    ChunkingMetrics,
    ContentChunk,
    NormalizedDocument,
    ParsedDocument,
)
from knowledge_system.domain.ingestion import SourceEnvelope


class ContentParser(Protocol):
    """Parse one bounded source envelope without executing its content."""

    def parse(self, envelope: SourceEnvelope) -> ParsedDocument: ...


class ContentNormalizer(Protocol):
    """Normalize untrusted text and apply deterministic metadata policy."""

    def normalize(self, parsed: ParsedDocument) -> NormalizedDocument: ...


class ContentChunker(Protocol):
    """Emit bounded, metadata-complete chunks for later indexing."""

    def chunk(
        self, document: NormalizedDocument
    ) -> tuple[tuple[ContentChunk, ...], ChunkingMetrics]: ...
