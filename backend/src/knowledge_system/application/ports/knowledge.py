"""Typed ports for future content, retrieval, generation, and audit adapters."""

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
    AuthorizedObjectId,
    CandidateEnvelope,
    EvidenceId,
    PrincipalContext,
)

# These aliases keep the original architecture vocabulary while the richer P10
# contracts carry source locators, lineage, limits, and security metadata.
Parser = ContentParser
Normalizer = ContentNormalizer
Chunker = ContentChunker


Embedder = EmbeddingProvider


class SearchBackend(Protocol):
    """Returns metadata-only candidates under server-generated constraints."""

    def search(self, query: str, tenant_id: str) -> Sequence[CandidateEnvelope]: ...

    def fetch_authorized_text(
        self, object_id: AuthorizedObjectId, tenant_id: str
    ) -> AuthorizedChunk: ...


AuthorizationService = AuthorizationPort


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
