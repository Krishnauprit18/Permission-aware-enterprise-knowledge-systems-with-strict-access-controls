# Retrieval Evaluation Hook

P12 exposes retrieval-only evidence for later evaluation. Runtime code does
not contain expected answers or generate golden labels.

`RetrievalResult.evaluation_record()` provides:

- ranked chunk IDs and resource IDs;
- the request authorization fingerprint;
- deterministic RRF component ranks/scores and fused scores;
- `unauthorized_context_rate`, which must be zero for the fixture corpus.

The record contains no question, chunk text, vector, prompt, model output, or
denied-resource detail. A later harness can join ranked IDs to the versioned
golden dataset and calculate retrieval metrics such as recall@k, precision@k,
MRR, nDCG, authorized-candidate recall, refusal correctness, and unauthorized
candidate rate. Generation metrics are not inferred from these records.

The first P12 security suite uses synthetic candidates and current authorization
fakes to prove three principals receive different sets, cross-tenant and
Legal-only decoys are excluded, revocation affects the next query without
re-embedding, client filters cannot widen scope, and the downstream-boundary
rate remains zero.
