# Evidence Resolution Evaluation

P13 keeps evidence-policy evaluation separate from retrieval ranking and future
generation quality. It consumes only authorized P12 candidates and records no
model answer or expected answer text in runtime code.

## Evaluation records

For each resolution run, evaluation may record stable evidence IDs, document and
version IDs, source groups, conflict groups, annotations, most-relevant ID,
most-authoritative ID, reranker/resolver versions, authorization fingerprint,
and content-free trace counts. Sanitized evidence text belongs to the protected
packet and is not copied into general evaluation telemetry.

## Required fixture assertions

The synthetic Acme timeline must establish all of the following:

- the old August customer target is retained as stale historical evidence;
- the later September planning note remains tentative, not an approval;
- the approved release-board record wins deterministic authority without
  erasing competing authorized evidence;
- the informal engineering concern remains a lower-authority concern and does
  not become a commitment;
- superseded approval versions retain lineage and annotations;
- duplicate/overlapping chunks collapse without losing source grouping;
- revoked or otherwise unauthorized material never reaches the text store,
  reranker, packet, or evaluator.

These assertions measure deterministic evidence correctness. They do not prove
retrieval recall, LLM truthfulness, citation validity, answer shareability, or
external audience policy; those remain separate evaluations.

## Local Semantic Reranker Evidence

The P13R acceptance check runs the pinned cache-only cross-encoder against an
authorized approved-release pair and an unrelated pair. It requires the former
to rank first and records the model/revision in the reranker version. This is
an adapter acceptance test, not a broad relevance-quality benchmark. Retrieval
metrics remain owned by the separate retrieval evaluation harness.
