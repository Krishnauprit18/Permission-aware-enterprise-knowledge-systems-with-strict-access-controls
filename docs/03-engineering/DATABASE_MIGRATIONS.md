# Database Migrations

## Source of truth

Ordered SQL files under `backend/migrations/` are the only schema authority.
The first migration is `0001_initial.sql`. Runtime application code does not
auto-create tables, run DDL, or infer schema from domain objects.

## Commands

```bash
make platform-config
make up
make db-migrate
make db-schema-doc
```

`make up` starts the local platform and then runs the explicit migration runner.
`make db-migrate` may be repeated safely. `make db-schema-doc` introspects the
live `knowledge` database and writes `docs/generated/db-schema.md`.

The runner creates only the migration ledger required to apply migrations,
checks each SQL file's SHA-256 against the stored checksum, and fails on drift.
Each newly applied migration and its ledger row share one transaction. A failed
migration rolls back and does not advance the ledger.

## Review rules

- Use a new four-digit, lexically sortable migration prefix.
- Keep DDL in the migration; do not hide schema changes in startup code.
- Include tenant-safe foreign keys, uniqueness, check constraints, and indexes.
- Use `timestamptz` for instants and write UTC-aware timestamps from Python.
- Prefer additive forward migrations; destructive changes require a retention,
  backup, rollback, and data-recovery plan in the phase evidence.
- Never store passwords, bearer tokens, private keys, raw connector secrets, or
  complete model context in canonical tables.
- Update the generated schema document after applying the migration locally.

## Failure triage

An unavailable PostgreSQL service is an operational failure, not permission to
skip migrations. A checksum mismatch means the applied migration history and
repository disagree; stop, restore the reviewed file or create a new forward
migration, and do not edit the ledger by hand. Foreign-key or uniqueness
failures indicate invalid source data or a non-idempotent write and must be
surfaced as typed persistence errors.
