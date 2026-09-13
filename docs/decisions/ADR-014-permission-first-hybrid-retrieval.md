# ADR-014: Permission-First Hybrid Retrieval

## Status

Accepted for P12.

## Context

The system must combine lexical and semantic search without allowing an
OpenSearch result, stale index metadata, or client filter to grant access. A
retrieved chunk must not reach reranking or any model-facing boundary unless
current authorization has allowed its resource.

## Decision

Resolve an OpenFGA-backed `can_view` scope first, create a frozen server-owned
authorization filter, and intersect all user filters with it. Run BM25 and
vector search inside that filter using metadata-only candidate responses.
Fuse the component lists with deterministic RRF, fine-check each resource
against current authorization, and return only authorized text-free candidate
metadata. Query embedding occurs only after a non-empty authorized scope is
established. OpenSearch remains a disposable recall structure, not an
authorization source.

## Alternatives considered

- Broad search followed by answer filtering: rejected because candidate scores,
  text, reranking, citations, or model context can disclose unauthorized data.
- Vector-only search: rejected because exact identifiers, dates, and policy
  language require lexical BM25 recall as well as semantic recall.
- Index-only ACL filtering: rejected because index metadata can be stale or
  tampered with; current OpenFGA and lifecycle checks remain authoritative.
- Per-request text fetch followed by authorization: rejected because it crosses
  the protected text boundary too early.

## Consequences

The initial `list-objects` scope enumeration is bounded by local corpus size and
requires later scale measurement. Candidate recall can degrade when a grant has
not reached the index, but revocation cannot disclose content because fine
checks occur before any downstream text-bearing stage. RRF is explainable and
deterministic; later reranking is a separate phase and accepts only authorized
types.

## Verification

P12 tests assert mandatory tenant/resource filters on both search branches,
metadata-only candidate parsing, different results by principal, cross-tenant
and Legal-only exclusion, immediate revocation behavior, fail-closed
authorizer failure, filter injection resistance, deterministic fusion, and a
zero unauthorized-context-rate fixture metric.
