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
    PrincipalContext,
)
from knowledge_system.domain.evidence import (
    EvidenceMaterial,
    EvidenceResolution,
    EvidenceResolutionInput,
    RerankScore,
)
from knowledge_system.domain.generation import (
    AuthorizedGenerationContext,
    GenerationTrace,
    ModelDraft,
)
from knowledge_system.domain.retrieval import EffectiveSearchFilter, RetrievalCandidate

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

    @property
    def reranker_version(self) -> str: ...

    def rerank(
        self,
        query: str,
        chunks: Sequence[AuthorizedChunk],
        *,
        limit: int,
        timeout_ms: int,
    ) -> Sequence[RerankScore]: ...


class EvidenceContentStore(Protocol):
    """Loads text only for the reauthorized P12 candidate subset."""

    def load(
        self, candidates: Sequence[RetrievalCandidate]
    ) -> Sequence[EvidenceMaterial]: ...


class EvidenceResolver(Protocol):
    """Applies deterministic policy to already-authorized loaded evidence only."""

    @property
    def resolver_version(self) -> str: ...

    def resolve(
        self,
        inputs: Sequence[EvidenceResolutionInput],
        *,
        correlation_id: str,
        authorization_fingerprint: str,
        reranker_version: str,
        input_candidate_count: int,
        reauthorized_candidate_count: int,
        authorization_drop_count: int,
    ) -> EvidenceResolution: ...


class LLM(Protocol):
    """Generates from an explicitly supplied authorized context."""

    def generate(self, query: str, context: Sequence[AuthorizedChunk]) -> str: ...


class GroundedLLM(Protocol):
    """Produces schema-first drafts from one already-authorized evidence package."""

    @property
    def model_id(self) -> str: ...

    @property
    def model_version(self) -> str: ...

    def generate(
        self, context: AuthorizedGenerationContext, *, retry: bool
    ) -> ModelDraft: ...


class GenerationTraceSink(Protocol):
    """Records content-free model/citation trace metadata."""

    def record(self, trace: GenerationTrace) -> None: ...


class AuditSink(Protocol):
    """Accepts structured, redacted audit events."""

    def record(self, event_name: str, principal: PrincipalContext) -> None: ...
