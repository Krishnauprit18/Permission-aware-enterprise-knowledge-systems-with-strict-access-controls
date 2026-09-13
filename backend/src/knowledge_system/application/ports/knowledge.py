"""Typed ports for future ingestion, retrieval, generation, and audit adapters."""

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Protocol

from knowledge_system.domain.contracts import (
    AuthorizationDecision,
    AuthorizedChunk,
    AuthorizedObjectId,
    CandidateEnvelope,
    EvidenceId,
    PrincipalContext,
)


class Connector(Protocol):
    """Reads source records without deciding application authorization."""

    def fetch_changed(self, since: datetime | None) -> Iterable[bytes]: ...


class Parser(Protocol):
    """Converts one raw record into normalized, untrusted content."""

    def parse(self, raw_record: bytes) -> str: ...


class Chunker(Protocol):
    """Splits normalized content into bounded, metadata-associated segments."""

    def chunk(self, normalized_text: str) -> Sequence[str]: ...


class Embedder(Protocol):
    """Produces embeddings through a local model adapter."""

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class SearchBackend(Protocol):
    """Returns metadata-only candidates under server-generated constraints."""

    def search(self, query: str, tenant_id: str) -> Sequence[CandidateEnvelope]: ...

    def fetch_authorized_text(
        self, object_id: AuthorizedObjectId, tenant_id: str
    ) -> AuthorizedChunk: ...


class AuthorizationService(Protocol):
    """Evaluates current relationships; implementations must fail closed."""

    def check_view(
        self, principal: PrincipalContext, object_id: AuthorizedObjectId
    ) -> AuthorizationDecision: ...


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
