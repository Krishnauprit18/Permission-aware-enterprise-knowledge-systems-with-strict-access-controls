# Evaluations

Retrieval and generation quality are measured separately. Golden data, metrics, refusal cases, access-control cases, and reproducible evaluation evidence will be added here.

`permission_matrix.json` is the deterministic authorization fixture for later
golden evaluations. It covers tenant/account membership, department and group
inheritance, direct restricted access, cross-tenant denial, and the separate
external-sharing relation. It contains identifiers and policy expectations only;
it contains no source content or credentials.

`SYNTHETIC_DATASET.md` documents the checked-in multi-source demo/evaluation
corpus, its evidence timeline, OpenFGA tuple inputs, and validation contract.

`RETRIEVAL_EVALUATION.md` documents the P12 retrieval-only evaluation hook and
keeps retrieval metrics separate from future generation evaluation.

`EVIDENCE_RESOLUTION_EVALUATION.md` documents P13 deterministic authority,
freshness, conflict, lineage, and authorization-boundary assertions separately
from retrieval and generation quality.

`EVALUATION_HARNESS.md` documents the P18 versioned golden-case contract,
independent retrieval/generation evaluators, deterministic metrics, security
release gates, local report artifacts, and regression diff behavior.
