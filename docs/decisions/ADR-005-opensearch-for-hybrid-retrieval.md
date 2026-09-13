# ADR-005: OpenSearch for Hybrid Retrieval

- Status: `accepted`
- Date: 2026-09-13
- Owners: architecture and security engineering
- Related phase: P02

## Context

The product requires lexical and semantic retrieval, metadata filtering,
authorization-aware candidate selection, explainable component scores, versioned
indexes, and local operation. Retrieval evaluation must measure lexical,
semantic, and hybrid behavior separately.

## Decision

Use OpenSearch as the searchable derivative store for BM25, vector, and hybrid
candidate retrieval. Store tenant, account, department, classification,
lifecycle, resource/revision, and schema metadata with each chunk. Search filters
are server-generated from current authorization scope and intersected with
allowlisted user filters.

OpenSearch is not authorization truth. Candidate search returns metadata-only
envelopes; OpenFGA and lifecycle fine checks occur before text fetch, reranking,
evidence construction, or model context.

## Alternatives considered

- Vector-only database: rejected because lexical search, filter semantics,
  score inspection, and one-system hybrid retrieval are first-class requirements.
- PostgreSQL with vector extension: viable for a smaller corpus, but not selected
  because P02 prioritizes mature BM25 plus vector retrieval and search-specific
  index lifecycle/evaluation in one local service.
- Separate lexical and vector databases: rejected initially because duplicated
  metadata, result fusion, deletion, and authorization-filter consistency add
  avoidable operational and security complexity.

## Security and privacy impact

Search documents and embeddings are sensitive derivatives. Tenant filters are
mandatory, aliases are tenant-safe, client ACL filters are never trusted, and
fine authorization is required before text retrieval. Deletion and reindexing
must reconcile derivatives and aliases.

## Evidence and verification

Later tests must prove BM25/vector/hybrid behavior, tenant/account filter
intersection, metadata-only candidate responses, pre-rerank fine checks,
revocation with stale coarse metadata, vector probing resistance, index cutover,
and deletion reconciliation.

## Consequences

The local stack gains a dedicated search service and index lifecycle. It avoids
a second vector store and supports independent retrieval evaluation, at the cost
of operating OpenSearch alongside PostgreSQL.
