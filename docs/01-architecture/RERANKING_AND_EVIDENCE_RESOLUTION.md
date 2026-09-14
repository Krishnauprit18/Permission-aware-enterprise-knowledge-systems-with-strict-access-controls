# Reranking And Evidence Resolution

P13 starts with `P12` `RetrievalResult` values only. It does not issue a new
search, enumerate more resources, accept client resource IDs, or use an LLM to
interpret authority, freshness, lifecycle, or conflicts.

## Protected order

```text
authorized P12 candidates
  -> current can_view re-check for each candidate
  -> typed evidence-content store fetch for that approved subset only
  -> deterministic text sanitization and bounds check
  -> bounded local pairwise reranker
  -> deterministic evidence policy resolver
  -> EvidenceResolution / EvidencePacket
```

The re-check closes a revocation race between P12 candidate production and the
first text-bearing P13 operation. A denied candidate is not sent to the content
store, reranker, resolver, trace text field, context builder, or later model
boundary. Authorization-store failures raise a generic protected failure.

## Reranking

`LocalPairwiseReranker` is a local deterministic query-document pair scorer.
It compares bounded query and sanitized authorized text, then emits only a
score/rank for supplied stable evidence IDs. It is an offline baseline, not a
semantic-quality claim or authorization mechanism.

- Input is capped at 20 authorized materials by default, within the P12 bound.
- A 250 ms local timeout is enforced during scoring.
- Returned IDs must be a unique subset of supplied IDs. Unknown or duplicate
  IDs cause safe fallback rather than candidate admission.
- Explicit reranker timeout/unavailability preserves P12's already-authorized
  order. Fallback does not reload, search, or widen authorization.

## Evidence policy

The typed content store returns source text with trusted policy metadata. Text,
query terms, model outputs, and relevance scores cannot populate or override
that metadata.

`EvidencePolicyMetadata` contains authority level, effective timestamp,
freshness, lifecycle, represented business status, conflict group, and explicit
supersession links. Only active material can enter resolution. A production
adapter must obtain these values from canonical lifecycle/policy records; the
P13 test adapter supplies synthetic deterministic fixtures.

The resolver:

- normalizes untrusted source text using the P10 safe normalizer;
- derives a stable evidence ID from chunk and document-version identity;
- collapses exact duplicates and high-overlap adjacent chunks from one document
  version while retaining a duplicate count in the trace;
- groups remaining chunks by document/version for traceability;
- annotates current, stale, superseded, superseding, tentative, approved,
  committed, conflicting, and lower-authority evidence;
- preserves every non-duplicate authorized conflict item instead of averaging
  or silently discarding it;
- exposes `most_relevant_evidence_id` from rerank order and
  `most_authoritative_evidence_id` from deterministic policy order as separate
  fields.

Authority order uses current/supersession state, trusted authority level,
represented status, and effective timestamp. It never treats lexical/vector or
reranker score as a source-of-authority signal.

## Evidence packet contract

An `EvidencePacket` holds a stable evidence/chunk/document/version identity,
sanitized text, source type/locator/URL, update and effective timestamps,
authority/freshness/business status, classification/external-shareability,
conflict/supersession annotations, authorization fingerprint, and internal rank
diagnostics. Diagnostics are trace-only and must not be serialized into a user
answer by a later phase.

P13 does not decide `can_share_externally`, create citations, build LLM context,
or generate a response. Later phases must re-use this packet and separately
enforce sharing/citation policy.
