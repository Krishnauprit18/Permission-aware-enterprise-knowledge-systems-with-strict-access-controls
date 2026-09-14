# Versioning Strategy

Version identifiers are explicit inputs to traces, checkpoints, caches, and
evaluation evidence. Mutable aliases may route traffic, but immutable versions
remain recoverable and auditable.

## 1. API version

- Public HTTP paths begin with `/api/v1`.
- Additive optional fields and endpoints may remain in `v1`; removals, semantic
  changes, authorization changes, or incompatible field changes require `v2`.
- Every response includes a stable request/correlation ID. Evidence and audit
  schemas carry their own schema version rather than assuming API version.
- OpenAPI output is generated from strict typed contracts and checked for
  unintended breaking changes once implementation exists.
- Frontend and backend compatibility is verified in Docker Compose before a
  checkpoint/release.

## 2. OpenSearch index schema version

- Physical index names include an immutable schema generation, for example
  `knowledge-chunks-v1-000001`; a stable read alias points to the active
  generation.
- `index_schema_version` covers mappings, analyzers, filter fields, lifecycle
  fields, stored text shape, and vector mapping.
- Breaking mapping/analyzer/vector changes require a new physical index and
  controlled reindex from canonical source/revision data.
- Cutover requires count, tenant-isolation, ACL-filter, retrieval, and deletion
  reconciliation. Rollback changes the alias to a verified prior generation.
- Mixed schema versions cannot be merged into one evidence package unless an
  explicitly tested compatibility rule allows it.

## 3. Embedding version

An immutable `embedding_version` identifies adapter family, configured model
artifact/revision, vector dimension, normalization, preprocessing, and content
language policy. Model names are configuration, not hard-coded business logic.

A dimension, model artifact, preprocessing, or normalization change creates a
new embedding version and normally a new index generation. Old and new vectors
are never compared as though they share one score space. Authorization
relationship changes do not change embedding version and never require
re-embedding.

## 4. Prompt version

- Each system/task prompt has a stable purpose ID, semantic version, and content
  SHA-256.
- Published prompt versions are immutable. A content change creates a new
  version and evaluation run.
- Prompt configuration references evidence schema, output schema, citation
  contract, and compatible model-adapter capabilities.
- Prompts contain no secrets or authorization decisions. Retrieved text is
  inserted only in the delimited evidence-data section. P14's trusted prompt is
  `grounded-answer:v1`; its SHA-256 is recorded in every `GenerationTrace` and
  changes only with a new prompt version.
- Traces record prompt purpose/version/hash without storing complete protected
  context by default.

## 5. Evaluation dataset version

- Golden datasets use `MAJOR.MINOR.PATCH` plus a content hash and immutable
  question IDs.
- `MAJOR`: changed task definition, policy semantics, metric contract, or corpus
  authorization model that breaks comparison.
- `MINOR`: added questions/sources/personas or expanded expected evidence while
  retaining metric compatibility.
- `PATCH`: corrected metadata, typo, or expectation without changing intended
  behavior.
- Retrieval and generation results record dataset version/hash separately, along
  with index, embedding, reranker, resolver, prompt, and model versions.
- Sensitive or unauthorized expected evidence is identified by stable synthetic
  IDs and is never placed into a model context merely to score a refusal.

## 6. Authorization model version

OpenFGA authorization model IDs and relation-schema changes are immutable
deployment inputs. Tuple changes use current relationship truth and a monotonic
change/checkpoint reference where available. Queries and audit events record the
model ID and consistency/freshness context. A model change requires authorization
matrix, revocation, cross-tenant, and shareability regression tests.

## 7. Database and object schema version

The current PostgreSQL schema generation is `0001_initial`. PostgreSQL schema
changes use ordered, checksum-verified migrations with upgrade and rollback or
forward-recovery evidence. Raw object manifests, normalized documents, chunks,
audit events, and pipeline checkpoints carry explicit schema/component versions.
Readers reject unknown incompatible versions rather than guessing.

## 8. Pipeline component version

Connector, parser, normalizer, ACL mapper, classifier, chunker, evidence resolver,
citation validator, generation prompt, local model adapter, confidentiality
policy, and policy-warning components expose immutable versions. The P15
confidentiality policy component is `confidentiality-policy-v1`.
Ingestion checkpoints record all versions that influence a derivative. A
behavior-changing version can schedule deterministic replay/reindex without
rewriting source history.

## 9. Release compatibility record

Each phase checkpoint/release records a compatibility tuple containing at least:

```text
api
database migration
OpenFGA model
index schema
embedding
reranker
evidence resolver
prompt
evaluation dataset
audit event schema
```

Unsupported tuples fail startup/readiness or protected operations explicitly.
They are never silently coerced on an authorization path.
