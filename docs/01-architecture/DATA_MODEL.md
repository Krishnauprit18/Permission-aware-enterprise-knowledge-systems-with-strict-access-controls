# Canonical Data Model

## Authority boundary

PostgreSQL is authoritative for tenant/account references, source provenance,
document version lineage, derivative lifecycle, ingestion progress, minimized
query trace metadata, evaluation metadata, and migration state. It is not the
source of identity secrets, source payload bytes, embeddings, semantic scores,
or current relationship authorization. Keycloak owns identity; OpenFGA owns
relationship decisions; MinIO owns raw objects; OpenSearch owns searchable
derivatives.

Every tenant-owned row carries `tenant_id` directly or through an enforced
foreign-key path. PostgreSQL metadata can make a resource unavailable because
it is deleted, but it cannot grant `can_view` or `can_share_externally` based on
a denormalized ACL flag. The OpenFGA check remains mandatory before protected
content is used.

## Entities

| Entity | Purpose | Sensitive boundary |
|---|---|---|
| `tenants` | Organization lifecycle and display metadata | No identity or source secrets |
| `principal_references` | Keycloak subject-to-tenant reference | No password, token, or credential material |
| `accounts` | Tenant-scoped customer account registry | Relationship membership remains OpenFGA truth |
| `source_connections` | Connector identity, endpoint, retention, and secret reference | `credentials_ref` is only an external secret-manager reference |
| `source_items` | Canonical document/source-item metadata and lifecycle | No document text; classification is trusted metadata, not authorization |
| `source_item_accounts` | Tenant-safe document/account association | Does not grant access by itself |
| `document_versions` | Immutable source revision and raw-object references | Raw bytes remain in MinIO |
| `chunks` | Stable searchable derivative metadata | No chunk text; OpenSearch payload is separately governed |
| `ingestion_jobs` | Durable job status and idempotency key | Error fields are codes, not credentials or payload dumps |
| `ingestion_checkpoints` | Connector cursor and committed source hash | Cursor is treated as source metadata and retained minimally |
| `deletion_tombstones` | Durable deletion/de-permission marker | Prevents stale replay and is retained through the deletion window |
| `query_traces` | Minimized query audit metadata and evidence IDs | Query text, raw model context, tokens, and vectors are not stored by default |
| `security_audit_events` | Typed login, authorization, lifecycle, policy, admin, and query audit events | Payload is minimized JSON metadata; subject references are pseudonymous |
| `evaluation_datasets` | Versioned evaluation set registry | Controlled test metadata only |
| `evaluation_cases` | Questions, expected evidence IDs, and refusal labels | Synthetic/local evaluation boundary |
| `evaluation_runs` | Retrieval/generation metrics and model-version references | Metrics only; no raw prompts or answers by default |

The generated column inventory is [db-schema.md](../generated/db-schema.md).
`backend/migrations/` is the schema source of truth; the generated document is
review evidence, not an input to runtime behavior.

## Metadata contract

`source_items` stores `source_type`, `source_external_id`, `source_url`,
`tenant_id`, account associations, department, timestamps, author,
classification, external-shareability, authority level, ACL relationship
references, current version, content hash, language, status, deletion time,
retention time, supersession, and lineage. `external_shareable` is constrained
to `PUBLIC` or `CUSTOMER_SHAREABLE`; it remains separate from `can_view`.

## Stable identity

The source item identity is `(tenant_id, source_type, source_external_id)`.
Document versions are identified by their immutable `version_id` and the
`(document_id, tenant_id, version)` uniqueness constraint. A chunk ID is the
SHA-256 digest of the canonical tuple:

```text
document_id | v<document_version> | <ordinal> | <chunk_content_hash>
```

The helper `stable_chunk_id()` produces the same ID for a deterministic
re-ingestion of the same version and chunk content. A content or version change
produces a new identity, allowing citation reconstruction to retain the exact
version boundary.

## Lifecycle and deletion

Active source items and chunks are query-eligible only after the later
authorization/retrieval phases apply current OpenFGA policy. A deleted item or
chunk requires `deleted_at`; a tombstone records source identity, reason,
effective time, and `retention_until`. Tombstones are idempotent by tenant and
source identity and block stale connector replay during retention.

The default policy is soft deletion plus derivative removal/tombstoning. Raw
objects may remain until an explicitly configured retention or legal hold ends,
but retained raw bytes are inaccessible to query and are not searchable. Hard
deletion is a separately authorized retention operation and must follow the
same audit and reconciliation path.

## Transaction boundaries

`PostgresUnitOfWork` owns one connection. Entering the unit of work starts an
explicit application transaction; normal exit commits, exceptional exit rolls
back, and the connection closes. `CanonicalPersistenceService` uses one unit
of work per operation. A caller that must atomically write several objects uses
one repository instance inside one unit of work.

The runtime repository never creates tables or alters schema. It expects the
explicit migration runner to have completed successfully.
