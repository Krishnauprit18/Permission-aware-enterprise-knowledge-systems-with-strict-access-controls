# Synthetic Dataset

## Purpose

`northstar-enterprise-demo-eval` is a deterministic, entirely synthetic corpus
for local demos and later retrieval/generation evaluation. It is a fixture
boundary, not a runtime answer store and not a substitute for source
connectors, ingestion, authorization, or model evaluation.

Validate it with:

```bash
make dataset-validate
```

The validator checks content hashes, stable identifiers, tenant references,
source metadata, OpenFGA-shaped ACL fixtures, lineage, lifecycle markers,
scenario labels, and the absence of secret-like material or email-shaped PII.

## Fixture Map

| File or directory | Purpose |
| --- | --- |
| `data/synthetic/manifest.json` | Versioned source-item metadata and evidence profiles |
| `data/synthetic/accounts.json` | Synthetic customer accounts and tenant ownership |
| `data/synthetic/users.json` | Synthetic principals, personas, groups, and account scope |
| `data/synthetic/acl-fixtures.json` | Source ACLs represented as OpenFGA tuple inputs |
| `data/synthetic/golden-cases.json` | 60 labeled retrieval/refusal cases without model answers |
| `data/synthetic/source/documents/` | Markdown document-like source fixtures |
| `data/synthetic/source/tickets/` | Support-ticket JSON fixtures |
| `data/synthetic/source/slack/` | Slack-style channel/thread JSON fixtures |
| `data/synthetic/source/calls/` | Call transcript fixture |
| `data/synthetic/source/policies/` | Restricted policy versions |
| `data/synthetic/source/feeds/` | Hourly-update source fixture |

The corpus contains Northstar tenant accounts Acme, Beacon, and Cedar, plus a
separate Harbor Labs tenant used only as a cross-tenant decoy. Personas cover
Account Manager, Product Manager, Support Engineer, Legal Counsel, and Finance
Analyst. No passwords, tokens, API keys, real contact details, or generated
answers are stored in the dataset.

## Evidence Timeline

The Acme launch-date conflict group is intentionally ordered by authority and
freshness rather than by retrieval convenience:

| Date | Evidence | Classification | Interpretation |
| --- | --- | --- | --- |
| 2026-08-03 | Customer statement targets 2026-08-15 | `CUSTOMER_SHAREABLE` | Old external expectation; stale |
| 2026-09-01 | Internal planning note tentatively targets 2026-09-10 | `INTERNAL` | Later but explicitly tentative; stale |
| 2026-09-05 | Signed approval v2 targets 2026-09-20 | `INTERNAL` | Authoritative but superseded |
| 2026-09-08 | Signed approval v3 sets 2026-09-24 09:00 UTC | `INTERNAL` | Current authoritative date |
| 2026-09-09 | Customer release note confirms 2026-09-24 | `CUSTOMER_SHAREABLE` | Customer-safe corroboration |
| 2026-09-09 | Engineering thread raises an informal rollout concern | `INTERNAL` | Relevant conflict signal, not approval authority |

The signed order form and current legal data-handling policy are restricted to
Legal. Older policy and approval versions remain indexed as superseded
lineage, while the Cedar incident is marked deleted and must not be returned.
The Beacon health feed has a declared 60-minute cadence and revision metadata.
The injection fixture is ordinary untrusted source text that attempts to
override instructions and request credentials; it has no authority.

## Authorization Fixtures

Each manifest item has exactly one `resource:<source-item-id>` record in
`acl-fixtures.json`. Tuple subjects use the existing OpenFGA namespace:
`user:`, `group:`, `account:`, `department:`, or `tenant:`. The fixture maps
account, group, department, direct viewer, Legal restricted-viewer, and
external share-reviewer relationships. The deleted fixture retains only its
tenant association and has no granting relation. The Harbor decoy has a
different tenant and account namespace.

These tuples are input data for later deterministic seeding and evaluation;
they do not bypass the backend authorization port. At query time the server
must resolve the caller's current relationship scope and enforce `can_view`
before any chunk can reach an LLM context. `external_shareable` is metadata
for a separate `can_share_externally` policy decision, never a view grant.

## Evaluation Contract

The 60 golden cases are grouped across easy lookup, synthesis, conflicts and
staleness, refusal and isolation, customer-safe sharing, role revocation,
hourly updates, deletion, and lineage. Every case declares:

- a principal and tenant;
- scenario labels;
- expected evidence IDs or an explicit refusal;
- retrieval outcome;
- authority expectation;
- freshness expectation.

Expected evidence IDs are retrieval-evaluation expectations. They are not
answers for a language model. Generation evaluation will consume only the
validated evidence returned by the retrieval pipeline and will assess
grounding, citation validity, refusal behavior, and shareability policy
separately.

## Change Protocol

When changing a source fixture, update its manifest `content_hash` with a
reviewable SHA-256 change, preserve deterministic timestamps and IDs unless a
new version is intended, and update labels/cases/ACLs together. Run
`make dataset-validate`, the focused dataset tests, and the applicable full
phase gates. Do not add real-looking credentials or contact data to make a
fixture feel realistic.
