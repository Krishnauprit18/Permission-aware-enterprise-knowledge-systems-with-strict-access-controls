# P18 Evaluation Harness

P18 provides a local, deterministic harness for the versioned synthetic
corpus. It evaluates two independent streams:

1. **Retrieval** consumes ranked, text-free candidate IDs and authorization
   metadata. It measures ranking quality and whether protected IDs crossed the
   context boundary.
2. **Generation** consumes structured answer metadata only: claim rubric keys,
   citation IDs, citation support, refusal state, conflict/temporal handling,
   and policy warning codes. It does not infer retrieval quality.

The evaluator never stores source text, vectors, raw model answers, hidden
reasoning, credentials, or chain-of-thought. Expected claim keys are rubric
labels, not hand-written runtime answers.

## Golden contract

`data/synthetic/golden-cases.json` contains 60 deterministic cases and is
versioned independently from code. The P08 records retain concise source
metadata. `GoldenCase.from_json` promotes each case to the P18 contract with:

- `principal`, `tenant_id`, `query`, and `mode`;
- relevant IDs, derived forbidden IDs, and citation IDs;
- answer-free claim rubric keys;
- conflict, refusal, freshness, authority, and warning expectations.

The derivation is deterministic from trusted manifest metadata and scenario
labels. A future dataset revision may provide explicit values in each case;
explicit values take precedence. `make dataset-validate` checks the promoted
contract as well as the source hashes, ACLs, tenant boundaries, and lifecycle
markers.

## Commands

The fast local smoke run is:

```bash
make eval
```

It writes the ignored, versioned directory `reports/evals/1.1.0/`:

| Artifact | Contents |
| --- | --- |
| `summary.json` | Versioned aggregate report and security gate status |
| `retrieval.json` | Retrieval-only metrics |
| `generation.json` | Generation-only metrics |
| `summary.md` | Human-readable report |
| `summary.html` | Escaped local browser report |
| `regression-diff.json` | Numeric changes from the previous report, if present |

The default run is `contract_fixture_smoke`. It is an oracle-shaped harness
smoke baseline proving schemas and metric plumbing; it is not a claim about
semantic retrieval or model quality. A real protected pipeline can supply
paired JSON arrays:

```bash
uv run --directory backend python -m knowledge_system.evaluation \
  --retrieval-observations /path/to/retrieval.json \
  --generation-observations /path/to/generation.json \
  --output-dir reports/evals/1.1.0 \
  --previous-report reports/evals/prior/summary.json
```

Retrieval observations are text-free and contain `case_id`, `ranked_ids`,
`allowed_ids`, `context_ids`, `tenant_by_id`, and optional `relevance_grades`.
Generation observations contain `case_id`, `refused`, `claim_keys`,
`citation_ids`, `supported_citation_ids`, `conflict_handled`,
`temporal_correct`, `warning_codes`, `invalid_citation_accepted`, and
`provided_evidence_ids`. These are protected-pipeline output contracts, not
client API input.

## Metrics

Retrieval calculates Recall@1/3/5/10, Precision@1/3/5/10 where the case has
relevant IDs, MRR, and graded nDCG. Empty/refusal cases are excluded from
ranking-quality denominators. Security metrics count context IDs outside the
observed authorization scope and context IDs whose tenant is not the case
tenant.

Generation calculates deterministic grounded correctness against claim rubric
keys, citation precision/recall/support, conflict handling, temporal
correctness, refusal correctness, and warning correctness. Citation support is
the fraction of observed citation IDs present in the backend-supported set.

## Release-blocking security gates

The following must be exactly zero:

| Metric | Definition | Action |
| --- | --- | --- |
| Unauthorized Context Rate | Context IDs not in the current authorized ID set divided by context IDs | Any nonzero value blocks the run |
| Cross-Tenant Leakage | Context IDs whose trusted tenant metadata differs from the case tenant | Any nonzero count blocks the run |
| Invalid Citation Acceptance | Unknown accepted citation IDs plus explicitly reported invalid acceptances | Any nonzero count blocks the run |

These are deterministic security oracles. An optional future local LLM judge
may advise on nuanced faithfulness, but it must be default-off and can never
override these gates or be the sole generation-quality oracle.

## Regression interpretation

`regression-diff.json` contains numeric metric changes only. It never diffs
questions, source text, answer text, URLs, or model prompts. A changed metric
requires review of the dataset version, observed pipeline records, model/index
versions, and authorization fingerprint before acceptance.

## Evidence boundary and limitations

P18 evaluates supplied records; it does not manufacture live OpenSearch,
OpenFGA, model, or browser traffic. The default smoke baseline therefore
proves contract behavior and security arithmetic, not end-to-end quality. Live
pipeline observations, measured relevance quality, and a broad semantic judge
remain operational evidence for later runs.
