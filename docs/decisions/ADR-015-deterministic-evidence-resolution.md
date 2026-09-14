# ADR-015: Deterministic Evidence Resolution

- Status: accepted
- Date: 2026-09-14
- Owners: Engineering
- Related phase: P13

## Context

Authorized candidates can still contain stale statements, planning notes,
superseded records, duplicate chunk windows, and lower-authority concerns.
Relevance cannot decide which evidence is authoritative, and an LLM cannot be a
source of authority or security classification.

## Decision

Re-check `can_view` before the first P13 text fetch. Load text only through
`PostgresMinioEvidenceContentStore` for that approved subset. The adapter
validates active canonical source/version/chunk metadata, reads a bounded and
SHA-256-verified MinIO snapshot, then reconstructs and validates the P10 chunk
before returning text. Sanitize it with the P10 normalizer and run the bounded
cache-only FastEmbed `Xenova/ms-marco-MiniLM-L-6-v2` ONNX cross-encoder, pinned
at revision `a09144355adeed5f58c8ed011d209bf8ee5a1fec`. Feed only the resulting
authorized materials to a deterministic resolver that uses trusted policy
metadata for lifecycle, authority, effective time, status, conflict groups, and
supersession links. The lexical scorer is retained for deterministic tests and
safe fallback behavior only.

The resolver emits stable `EvidencePacket` values, source groups, conflict
records, and separate most-relevant and most-authoritative IDs. It retains
contradictory authorized evidence with annotations. A reranker failure falls
back to the existing authorized P12 order and cannot invoke retrieval.

## Alternatives considered

- Use reranker relevance as authority: rejected because a score cannot prove an
  approval, lifecycle state, or source legitimacy.
- Ask an LLM to resolve conflicts: rejected because source text and model output
  are untrusted and cannot make authority/security decisions.
- Fetch broad text then filter before context: rejected because text would cross
  the protected authorization boundary.
- Drop all conflicting or superseded evidence: rejected because it hides useful
  provenance and makes conflict handling unauditable.

## Security and privacy impact

Current authorization is rechecked before text-bearing operations. Missing or
malformed security metadata, authorization failure, content-store mismatch, and
invalid reranker output fail closed. The packet retains classification and
shareability but does not grant external sharing, generate citations, or build
an LLM context.

## Evidence and verification

`backend/tests/unit/test_evidence_resolution.py` covers the Acme August/
September/approved/conflict sequence, tentative/approved status, lower-authority
engineering concern, duplicate collapse, supersession, current authorization,
and local reranker fallback. P13R adds a cache-only semantic-reranker acceptance
test and an opt-in real PostgreSQL/MinIO test that reconstructs one canonical
chunk and rejects altered citation locators.

## Consequences

The pinned local cross-encoder is a real semantic adapter, but its acceptance
test is not a broad relevance-quality benchmark. The production-shaped
content-store adapter has a real local PostgreSQL/MinIO integration path; any
policy-rule change requires a resolver-version change and evidence evaluation.
