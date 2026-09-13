"""Typed ports for content, retrieval, generation, and audit adapters."""

from collections.abc import Sequence
from typing import Protocol

from knowledge_system.application.ports.authorization import AuthorizationPort
from knowledge_system.application.ports.content import (
    ContentChunker,
    ContentNormalizer,
    ContentParser,
)
from knowledge_system.application.ports.indexing import EmbeddingProvider
from knowledge_system.domain.contracts import (
    AuthorizedChunk,
    CandidateEnvelope,
    EvidenceId,
    PrincipalContext,
)
from knowledge_system.domain.retrieval import EffectiveSearchFilter

# These aliases keep the original architecture vocabulary while the richer P10
# contracts carry source locators, lineage, limits, and security metadata.
Parser = ContentParser
Normalizer = ContentNormalizer
Chunker = ContentChunker


Embedder = EmbeddingProvider


class SearchBackend(Protocol):
    """Returns metadata-only candidates under server-generated constraints."""

    def search_bm25_candidates(
        self,
        query: str,
        filters: EffectiveSearchFilter,
        size: int,
        *,
        index_name: str = "knowledge-chunks-active",
    ) -> Sequence[CandidateEnvelope]: ...

    def search_vector_candidates(
        self,
        vector: Sequence[float],
        filters: EffectiveSearchFilter,
        size: int,
        *,
        index_name: str = "knowledge-chunks-active",
    ) -> Sequence[CandidateEnvelope]: ...


AuthorizationService = AuthorizationPort


class QueryEmbedder(Protocol):
    """Embeds only the bounded query string after authorization scope resolution."""

    provider: EmbeddingProvider


class Reranker(Protocol):
    """Ranks already-authorized chunks only."""

    def rerank(
        self, query: str, chunks: Sequence[AuthorizedChunk]
    ) -> Sequence[AuthorizedChunk]: ...


class LLM(Protocol):
    """Generates from an explicitly supplied authorized context."""

    def generate(self, query: str, context: Sequence[AuthorizedChunk]) -> str: ...


class EvidenceResolver(Protocol):
    """Resolves citations only against supplied evidence IDs."""

    def resolve(self, evidence_ids: Sequence[EvidenceId]) -> Sequence[EvidenceId]: ...


class AuditSink(Protocol):
    """Accepts structured, redacted audit events."""

    def record(self, event_name: str, principal: PrincipalContext) -> None: ...
