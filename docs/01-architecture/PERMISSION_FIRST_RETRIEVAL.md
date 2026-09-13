# Permission-First Hybrid Retrieval

## Scope

P12 implements the query path through authorized, metadata-only candidate
results. It stops before reranking, evidence resolution, context construction,
citation validation, answer generation, and external sharing.

The application entry point accepts a validated `PrincipalContext` and a
bounded `RetrievalRequest`. It does not accept OpenSearch JSON, tenant IDs,
resource IDs, or ACL filters as authorization inputs from the client.

## Request ordering

1. Resolve the current `can_view` scope from the OpenFGA-backed authorization
   port using the authenticated principal.
2. Build an immutable `AuthorizationFilter` from that scope. The filter binds
   the principal tenant, trusted resource IDs, policy/model versions, and the
   decision fingerprint.
3. Intersect typed optional account, department, and UTC update-time filters
   with the authorization filter. These constraints can only reduce results.
4. If the scope is empty, return an empty candidate result without embedding or
   searching the question.
5. Embed the bounded question locally, then run BM25 and vector search with the
   same effective filter. OpenSearch returns allowlisted metadata only; text
   and vectors are excluded from candidate `_source` fields.
6. Fuse the two ranked lists with deterministic Reciprocal Rank Fusion
   (`1 / (rrf_k + rank)`, default `rrf_k=60`) and stable chunk-ID tie breaks.
7. Fine-check every fused resource against current OpenFGA authorization. Only
   an explicit `ALLOW` decision creates a `RetrievalCandidate`.
8. Return authorized candidates with provenance, citation locators, and the
   decision fingerprint. No text-bearing type is constructed in P12.

## Filter construction

`AuthorizationFilter` is frozen and server-created. Its trusted OpenFGA
`resource:<document-id>` references are translated to canonical index document
IDs only inside the adapter. Every query clause contains a mandatory tenant
term and the authorized document-ID terms. An empty authorized scope becomes a
`match_none` clause and never becomes an unfiltered query.

The client filter object is an allowlisted typed value with bounded account
IDs, department, and UTC date range. There is no raw query DSL or client tenant
field. OpenSearch metadata is a recall/defense-in-depth constraint and never a
grant; the current fine check remains authoritative.

## Authorization and failure posture

Authorization scope failures, malformed scope data, and authorizer timeouts
raise the generic protected-path `RetrievalAuthorizationError` and occur before
query embedding or search. Search/model dependency failure produces no partial
protected result. A malformed, cross-tenant, or out-of-scope candidate is
dropped before the fine check; a denied or indeterminate fine check is dropped
before the result can reach later reranking or context code.

The P12 trace records only correlation, scope/fingerprint, counts, denial
counts, and text-free lexical/vector rank diagnostics. `unauthorized_context_count`
is an explicit regression metric and must remain zero. The result exposes no
raw chunk text, vector, OpenSearch response, or denied-resource detail.

## ListObjects performance boundary

The current OpenFGA adapter uses `list-objects` to construct a metadata-only
scope, then performs restricted-resource rechecks. This is suitable for the
small local corpus but has a cardinality and latency cost proportional to the
enumerated resource set. The query service therefore has bounded result and
component limits and no cross-request scope cache. Future scale work must keep
the `AuthorizationPort` boundary and may replace enumeration with a bounded
authorization-aware search integration or change-stream-backed scope index;
that change requires measured latency/recall/revocation evidence and must keep
the fine-check-before-text invariant.

## Evaluation hook

`RetrievalResult.evaluation_record()` returns ranked chunk/resource IDs,
authorization fingerprint, unauthorized-context rate, and component
diagnostics. It intentionally excludes the question and source text so
retrieval evaluation can be persisted or compared without creating a new
model-context or logging channel. Generation evaluation remains a separate
future phase.
