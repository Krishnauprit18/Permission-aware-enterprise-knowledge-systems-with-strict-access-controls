"""Security tests for permission-first hybrid retrieval."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import cast

import pytest

from knowledge_system.adapters.search.opensearch import (
    OpenSearchIndexAdapter,
    OpenSearchResponse,
    OpenSearchTransport,
)
from knowledge_system.application.ports.authorization import (
    AuthorizationScope,
    AuthorizationUnavailable,
)
from knowledge_system.application.retrieval import PermissionFirstRetrievalService
from knowledge_system.domain.contracts import (
    AuthorizationDecision,
    AuthorizationOutcome,
    AuthorizationRelation,
    AuthorizedObjectId,
    CandidateEnvelope,
    PrincipalContext,
    PrincipalId,
)
from knowledge_system.domain.embedding import (
    EmbeddingBatch,
    EmbeddingConfig,
    LocalHashEmbeddingProvider,
)
from knowledge_system.domain.retrieval import (
    AuthorizationFilter,
    EffectiveSearchFilter,
    RequestedQueryFilters,
    RetrievalAuthorizationError,
    RetrievalInputError,
    RetrievalRequest,
    fuse_rrf,
)

NOW = datetime(2026, 9, 13, tzinfo=UTC)


def principal(subject: str, tenant: str = "northstar") -> PrincipalContext:
    return PrincipalContext(
        subject_id=PrincipalId(subject),
        tenant_id=tenant,
        correlation_id=f"corr-{subject}",
    )


def envelope(
    document_id: str,
    *,
    tenant: str = "northstar",
    account: str = "acme",
    classification: str = "INTERNAL",
    score: float = 1.0,
) -> CandidateEnvelope:
    return CandidateEnvelope(
        object_id=AuthorizedObjectId(f"resource:{document_id}"),
        tenant_id=tenant,
        source="document",
        access_level=classification,
        chunk_id=f"chunk:{document_id}",
        document_id=document_id,
        document_version_id=f"{document_id}:v1",
        lexical_score=score,
        vector_score=score,
        provenance={
            "source_external_id": document_id,
            "account_ids": account,
            "department": "product",
            "citation_locators": f"document:{document_id}#section=Evidence",
            "updated_at": NOW.isoformat(),
            "source_url": f"https://docs.invalid/{document_id}",
            "status": "ACTIVE",
        },
    )


class FakeAuthorization:
    def __init__(self, allowed_by_subject: dict[str, set[str]]) -> None:
        self.allowed_by_subject = allowed_by_subject
        self.denied_on_check: set[str] = set()
        self.scope_calls = 0
        self.check_calls: list[str] = []

    def list_authorized_resource_ids(
        self,
        principal_value: PrincipalContext,
        relation: AuthorizationRelation = "can_view",
    ) -> AuthorizationScope:
        if relation != "can_view":
            raise AssertionError("P12 must request view scope")
        self.scope_calls += 1
        ids = tuple(
            AuthorizedObjectId(f"resource:{document_id}")
            for document_id in sorted(
                self.allowed_by_subject.get(str(principal_value.subject_id), set())
            )
        )
        return AuthorizationScope(
            tenant_id=principal_value.tenant_id,
            relation=relation,
            resource_ids=ids,
            authorization_model_id="model-p12",
            tuple_version="tuples-p12",
            policy_version="policy-p12",
            decision_fingerprint="f" * 64,
        )

    def check(
        self,
        principal_value: PrincipalContext,
        relation: AuthorizationRelation,
        object_id: AuthorizedObjectId,
    ) -> AuthorizationDecision:
        self.check_calls.append(str(object_id))
        resource_id = str(object_id).removeprefix("resource:")
        allowed = (
            resource_id
            in self.allowed_by_subject.get(str(principal_value.subject_id), set())
            and resource_id not in self.denied_on_check
        )
        return AuthorizationDecision(
            allowed=allowed,
            outcome=AuthorizationOutcome.ALLOW
            if allowed
            else AuthorizationOutcome.DENY,
            reason_code="allowed" if allowed else "relation_denied",
            authorization_model_id="model-p12",
            tuple_version="tuples-p12",
            policy_version="policy-p12",
            decision_fingerprint=("a" if allowed else "d") * 64,
            correlation_id=principal_value.correlation_id,
        )


class FailingAuthorization(FakeAuthorization):
    def list_authorized_resource_ids(
        self,
        principal_value: PrincipalContext,
        relation: AuthorizationRelation = "can_view",
    ) -> AuthorizationScope:
        del principal_value, relation
        raise AuthorizationUnavailable("dependency failed")


class FakeSearch:
    def __init__(self, candidates: Sequence[CandidateEnvelope]) -> None:
        self.candidates = tuple(candidates)
        self.filters: list[EffectiveSearchFilter] = []
        self.calls: list[str] = []

    def _select(self, filters: EffectiveSearchFilter) -> tuple[CandidateEnvelope, ...]:
        self.filters.append(filters)
        authorized = frozenset(filters.authorization.resource_ids)
        selected = tuple(
            candidate
            for candidate in self.candidates
            if candidate.object_id in authorized
            and (
                not filters.account_ids
                or any(
                    account in filters.account_ids
                    for account in candidate.provenance.get("account_ids", "").split(
                        ","
                    )
                )
            )
        )
        return selected

    def search_bm25_candidates(
        self,
        query: str,
        filters: EffectiveSearchFilter,
        size: int,
        *,
        index_name: str = "knowledge-chunks-active",
    ) -> Sequence[CandidateEnvelope]:
        del query, size, index_name
        self.calls.append("bm25")
        return self._select(filters)

    def search_vector_candidates(
        self,
        vector: Sequence[float],
        filters: EffectiveSearchFilter,
        size: int,
        *,
        index_name: str = "knowledge-chunks-active",
    ) -> Sequence[CandidateEnvelope]:
        del vector, size, index_name
        self.calls.append("vector")
        return self._select(filters)


class EmptySearchTransport(OpenSearchTransport):
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, object | None]] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: object | None = None,
        raw_body: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> OpenSearchResponse:
        del raw_body, headers
        self.requests.append((method, path, json_body))
        return OpenSearchResponse(200, {"hits": {"hits": []}})


class CountingEmbedder:
    def __init__(self) -> None:
        self.calls = 0
        self._provider = LocalHashEmbeddingProvider(
            EmbeddingConfig(dimension=8, batch_size=1)
        )

    def embed_batch(self, texts: tuple[str, ...]) -> EmbeddingBatch:
        self.calls += 1
        return self._provider.embed_batch(texts)


def service(
    authorization: FakeAuthorization,
    search: FakeSearch,
) -> PermissionFirstRetrievalService:
    config = EmbeddingConfig(dimension=8, batch_size=1)
    return PermissionFirstRetrievalService(
        authorization=authorization,
        search=search,
        query_embeddings=LocalHashEmbeddingProvider(config),
        rrf_k=10,
    )


@pytest.mark.unit
@pytest.mark.security
def test_three_principals_receive_different_authorized_candidate_sets() -> None:
    candidates = (
        envelope("acme-note"),
        envelope("beacon-ticket"),
        envelope("cedar-runbook"),
    )
    authorization = FakeAuthorization(
        {
            "alice": {"acme-note"},
            "miguel": {"beacon-ticket"},
            "priya": {"cedar-runbook"},
        }
    )
    search = FakeSearch(candidates)
    retrieval = service(authorization, search)

    results = {
        subject: retrieval.retrieve(
            principal(subject), RetrievalRequest("launch status")
        )
        for subject in ("alice", "miguel", "priya")
    }

    assert {
        subject: {candidate.document_id for candidate in result.candidates}
        for subject, result in results.items()
    } == {
        "alice": {"acme-note"},
        "miguel": {"beacon-ticket"},
        "priya": {"cedar-runbook"},
    }
    assert all(
        result.trace.unauthorized_context_rate == 0.0 for result in results.values()
    )


@pytest.mark.unit
@pytest.mark.security
def test_cross_tenant_and_legal_decoys_never_cross_authorized_boundary() -> None:
    candidates = (
        envelope("acme-note"),
        envelope("harbor-contract", tenant="harbor-labs"),
        envelope("legal-matter", classification="RESTRICTED"),
    )
    authorization = FakeAuthorization({"alice": {"acme-note"}})
    search = FakeSearch(candidates)
    result = service(authorization, search).retrieve(
        principal("alice"), RetrievalRequest("contract")
    )

    assert {candidate.document_id for candidate in result.candidates} == {"acme-note"}
    assert all(candidate.tenant_id == "northstar" for candidate in result.candidates)
    assert all(not hasattr(candidate, "text") for candidate in result.candidates)


@pytest.mark.unit
@pytest.mark.security
def test_fine_authorization_check_drops_candidate_before_downstream_boundary() -> None:
    authorization = FakeAuthorization({"alice": {"acme-note", "legal-matter"}})
    authorization.denied_on_check.add("legal-matter")
    result = service(
        authorization,
        FakeSearch((envelope("acme-note"), envelope("legal-matter"))),
    ).retrieve(principal("alice"), RetrievalRequest("policy"))

    assert [candidate.document_id for candidate in result.candidates] == ["acme-note"]
    assert result.trace.denied_candidate_count == 1
    assert result.trace.unauthorized_context_rate == 0.0


@pytest.mark.unit
@pytest.mark.security
def test_revocation_changes_next_query_without_reembedding() -> None:
    authorization = FakeAuthorization({"alice": {"acme-note"}})
    embedder = CountingEmbedder()
    search = FakeSearch((envelope("acme-note"),))
    retrieval = PermissionFirstRetrievalService(authorization, search, embedder)

    first = retrieval.retrieve(principal("alice"), RetrievalRequest("launch"))
    authorization.allowed_by_subject["alice"] = set()
    second = retrieval.retrieve(principal("alice"), RetrievalRequest("launch"))

    assert len(first.candidates) == 1
    assert second.candidates == ()
    assert embedder.calls == 1
    assert search.calls == ["bm25", "vector"]


@pytest.mark.unit
@pytest.mark.security
def test_authorization_failure_fails_closed_before_query_embedding_or_search() -> None:
    embedder = CountingEmbedder()
    search = FakeSearch((envelope("acme-note"),))
    retrieval = PermissionFirstRetrievalService(
        FailingAuthorization({}), search, embedder
    )

    with pytest.raises(RetrievalAuthorizationError, match="unavailable"):
        retrieval.retrieve(principal("alice"), RetrievalRequest("secret"))
    assert embedder.calls == 0
    assert search.calls == []


@pytest.mark.unit
@pytest.mark.security
def test_client_filters_only_narrow_authorized_scope_and_cannot_widen_it() -> None:
    authorization = FakeAuthorization({"alice": {"acme-note"}})
    search = FakeSearch(
        (envelope("acme-note"), envelope("beacon-ticket", account="beacon"))
    )
    result = service(authorization, search).retrieve(
        principal("alice"),
        RetrievalRequest(
            "status",
            RequestedQueryFilters(account_ids=("beacon",)),
        ),
    )

    assert result.candidates == ()
    assert search.filters[0].authorization.resource_ids == (
        AuthorizedObjectId("resource:acme-note"),
    )
    with pytest.raises(RetrievalInputError):
        RequestedQueryFilters(account_ids=("acme] OR match_all",))


@pytest.mark.unit
@pytest.mark.security
def test_rrf_is_deterministic_and_component_diagnostics_are_text_free() -> None:
    first = envelope("first", score=4.0)
    second = envelope("second", score=3.0)
    fused, diagnostics = fuse_rrf((first, second), (second, first), limit=2, rrf_k=10)

    assert tuple(candidate.chunk_id for candidate in fused) == (
        "chunk:first",
        "chunk:second",
    )
    assert diagnostics[0].lexical_rank == 1
    assert diagnostics[0].vector_rank == 2
    assert not hasattr(diagnostics[0], "text")


@pytest.mark.unit
@pytest.mark.security
def test_opensearch_candidate_paths_intersect_tenant_scope_and_hide_text() -> None:
    authorization = AuthorizationFilter(
        tenant_id="northstar",
        resource_ids=(AuthorizedObjectId("resource:acme-note"),),
        authorization_model_id="model",
        tuple_version="tuples",
        policy_version="policy",
        decision_fingerprint="f" * 64,
    )
    filters = EffectiveSearchFilter.intersect(
        authorization, RequestedQueryFilters(account_ids=("acme",))
    )
    transport = EmptySearchTransport()
    adapter = OpenSearchIndexAdapter(transport)

    adapter.search_bm25_candidates("status", filters, 5)
    adapter.search_vector_candidates((0.1, 0.2), filters, 5)

    for _method, _path, body in transport.requests:
        request_body = cast(dict[str, object], body)
        source_fields = cast(list[str], request_body["_source"])
        assert "text" not in source_fields
        assert "vector" not in source_fields
        query = cast(dict[str, object], request_body["query"])
        query_body = cast(dict[str, object], next(iter(query.values())))
        filter_body = cast(list[object], query_body.get("filter", []))
        serialized = str(request_body)
        assert "northstar" in serialized
        assert "acme-note" in serialized
        assert filter_body or "filter" in str(query_body)


@pytest.mark.unit
def test_retrieval_evaluation_hook_is_ranked_and_text_free() -> None:
    authorization = FakeAuthorization({"alice": {"acme-note"}})
    result = service(authorization, FakeSearch((envelope("acme-note"),))).retrieve(
        principal("alice"), RetrievalRequest("status")
    )

    record = result.evaluation_record()
    assert record.ranked_chunk_ids == ("chunk:acme-note",)
    assert record.ranked_resource_ids == ("resource:acme-note",)
    assert record.unauthorized_context_rate == 0.0
    assert not hasattr(record, "text")


@pytest.mark.unit
@pytest.mark.security
def test_malformed_authorization_scope_is_failed_closed() -> None:
    with pytest.raises(RetrievalAuthorizationError, match="unavailable"):
        AuthorizationFilter.from_scope(
            principal("alice"),
            AuthorizationScope(
                tenant_id="northstar",
                relation="can_view",
                resource_ids=(AuthorizedObjectId("document-without-resource-prefix"),),
                authorization_model_id="model",
                tuple_version="tuples",
                policy_version="policy",
                decision_fingerprint="f" * 64,
            ),
        )
