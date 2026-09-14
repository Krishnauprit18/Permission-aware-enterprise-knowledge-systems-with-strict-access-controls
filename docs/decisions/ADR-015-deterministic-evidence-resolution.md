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

Re-check `can_view` before the first P13 text fetch. Load text only through a
typed content store for that approved subset, sanitize it with the P10 normalizer,
and run a bounded local query-document pair scorer. Feed only the resulting
authorized materials to a deterministic resolver that uses trusted policy
metadata for lifecycle, authority, effective time, status, conflict groups, and
supersession links.

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
and local reranker fallback.

## Consequences

The local pairwise reranker is deterministic and offline but not a semantic
quality benchmark. A production content-store adapter and metadata projection
must be added before claiming end-to-end persisted evidence resolution. Any
policy-rule change requires a resolver-version change and evidence evaluation.
