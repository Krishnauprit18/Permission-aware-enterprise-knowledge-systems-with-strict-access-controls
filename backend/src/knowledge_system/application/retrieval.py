"""Permission-first hybrid retrieval through metadata-only candidates."""

from __future__ import annotations

from dataclasses import dataclass

from knowledge_system.application.ports.authorization import (
    AuthorizationPort,
    AuthorizationUnavailable,
)
from knowledge_system.application.ports.knowledge import SearchBackend
from knowledge_system.domain.contracts import AuthorizationOutcome, PrincipalContext
from knowledge_system.domain.embedding import EmbeddingError, EmbeddingProvider
from knowledge_system.domain.retrieval import (
    AuthorizationFilter,
    EffectiveSearchFilter,
    RetrievalAuthorizationError,
    RetrievalCandidate,
    RetrievalRequest,
    RetrievalResult,
    RetrievalTrace,
    candidate_from_envelope,
    fuse_rrf,
)


class RetrievalUnavailable(RuntimeError):
    """A retrieval dependency failed without producing a protected result."""


@dataclass(frozen=True, slots=True)
class PermissionFirstRetrievalService:
    """Resolve current authorization before either hybrid search branch."""

    authorization: AuthorizationPort
    search: SearchBackend
    query_embeddings: EmbeddingProvider
    index_name: str = "knowledge-chunks-active"
    rrf_k: int = 60

    def retrieve(
        self, principal: PrincipalContext, request: RetrievalRequest
    ) -> RetrievalResult:
        try:
            scope = self.authorization.list_authorized_resource_ids(
                principal, "can_view"
            )
            authorization_filter = AuthorizationFilter.from_scope(principal, scope)
        except (AuthorizationUnavailable, RetrievalAuthorizationError) as exc:
            raise RetrievalAuthorizationError(
                "authorized retrieval unavailable"
            ) from exc

        effective_filter = EffectiveSearchFilter.intersect(
            authorization_filter, request.filters
        )
        if not effective_filter.has_authorized_resources:
            return self._empty_result(principal, authorization_filter, 0)

        try:
            query_batch = self.query_embeddings.embed_batch((request.question,))
            query_vector = query_batch.vectors[0]
            lexical = self.search.search_bm25_candidates(
                request.question,
                effective_filter,
                request.component_limit,
                index_name=self.index_name,
            )
            vector = self.search.search_vector_candidates(
                query_vector,
                effective_filter,
                request.component_limit,
                index_name=self.index_name,
            )
        except (EmbeddingError, OSError, RuntimeError) as exc:
            raise RetrievalUnavailable("retrieval dependency unavailable") from exc

        # Treat the index filter as a recall optimization only. The service also
        # rejects malformed or cross-tenant envelopes before the current FGA check.
        allowed_resource_ids = frozenset(authorization_filter.resource_ids)
        lexical = tuple(
            candidate
            for candidate in lexical
            if candidate.tenant_id == principal.tenant_id
            and candidate.object_id in allowed_resource_ids
        )
        vector = tuple(
            candidate
            for candidate in vector
            if candidate.tenant_id == principal.tenant_id
            and candidate.object_id in allowed_resource_ids
        )
        fused, diagnostics = fuse_rrf(
            lexical, vector, limit=request.result_limit, rrf_k=self.rrf_k
        )

        authorized: list[RetrievalCandidate] = []
        denied = 0
        for candidate in fused:
            decision = self.authorization.check(
                principal, "can_view", candidate.object_id
            )
            if (
                decision.outcome is not AuthorizationOutcome.ALLOW
                or not decision.allowed
            ):
                denied += 1
                continue
            try:
                authorized.append(candidate_from_envelope(candidate, decision))
            except (RetrievalAuthorizationError, ValueError):
                denied += 1

        trace = RetrievalTrace(
            correlation_id=principal.correlation_id,
            authorization_fingerprint=authorization_filter.decision_fingerprint,
            authorized_scope_size=len(authorization_filter.resource_ids),
            coarse_candidate_count=len(fused),
            denied_candidate_count=denied,
            returned_candidate_count=len(authorized),
            # There is no text-bearing downstream transition in P12. This field
            # is an explicit regression metric for the future reranker boundary.
            unauthorized_context_count=0,
            component_diagnostics=diagnostics,
        )
        return RetrievalResult(tuple(authorized), trace)

    @staticmethod
    def _empty_result(
        principal: PrincipalContext,
        authorization_filter: AuthorizationFilter,
        coarse_count: int,
    ) -> RetrievalResult:
        return RetrievalResult(
            (),
            RetrievalTrace(
                correlation_id=principal.correlation_id,
                authorization_fingerprint=authorization_filter.decision_fingerprint,
                authorized_scope_size=len(authorization_filter.resource_ids),
                coarse_candidate_count=coarse_count,
                denied_candidate_count=0,
                returned_candidate_count=0,
                unauthorized_context_count=0,
            ),
        )
