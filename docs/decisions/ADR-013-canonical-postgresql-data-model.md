# ADR-013: Canonical PostgreSQL Data Model and Persistence Boundary

- Status: accepted
- Phase: P07
- Date: 2026-09-13

## Context

The system needs durable provenance, revision, lifecycle, ingestion, trace, and
evaluation metadata without duplicating identity secrets, searchable text, or
relationship authorization. Cross-store ingestion and deletion are not one
atomic transaction, so the database must make state transitions, idempotency,
lineage, and reconciliation explicit.

## Decision

Use PostgreSQL with ordered, checksum-verified SQL migrations and a typed
ports-and-adapters repository. Store canonical metadata in normalized tables for
tenants, principal references, accounts, source connections, source items,
document versions, chunks, jobs/checkpoints, tombstones, query traces, and
evaluation datasets/cases/runs. Use tenant-safe foreign keys, source identity
uniqueness, immutable version/chunk identity checks, lifecycle constraints, and
retention fields.

Use `psycopg` only in the infrastructure adapter. The application receives a
`CanonicalRepository` through an explicit `PostgresUnitOfWork`; normal exit
commits and exception exit rolls back. No runtime DDL or ORM auto-migration is
allowed.

Use soft deletion plus durable tombstones as the default. Remove or tombstone
searchable derivatives in the deletion pipeline; retained raw objects are not
queryable. OpenFGA remains the source of current authorization truth, and
PostgreSQL lifecycle state can deny but cannot grant access.

## Alternatives considered

- **ORM with startup auto-create:** rejected because implicit DDL obscures
  review, makes startup order nondeterministic, and weakens migration evidence.
- **Store all document/chunk text in PostgreSQL:** rejected because MinIO owns
  raw objects and OpenSearch owns searchable derivatives in the reference
  architecture; canonical rows keep references and metadata only.
- **PostgreSQL ACL flags as authorization:** rejected because stale flags cannot
  provide dynamic OpenFGA relationship truth or safe revocation.
- **Hard-delete immediately:** rejected because connector replay, audit,
  reconciliation, retention, and legal-hold handling require durable markers.

## Security and operational consequences

This design provides a durable tenant and lifecycle boundary, deterministic
re-ingestion/citation IDs, explicit rollback, and auditable deletion markers.
It does not make PostgreSQL the authorization engine or make cross-store
derivative removal atomic; the deletion saga and reconciliation tests remain
required before retrieval release.

## Evidence

- `backend/migrations/0001_initial.sql`
- `backend/src/knowledge_system/domain/persistence.py`
- `backend/src/knowledge_system/application/ports/persistence.py`
- `backend/src/knowledge_system/adapters/persistence/postgres.py`
- `backend/tests/integration/test_persistence_postgres.py`
- `docs/generated/db-schema.md`
