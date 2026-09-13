# ADR-010: Reference Application and Data Stack

- Status: `accepted`
- Date: 2026-09-13
- Owners: architecture and engineering
- Related phase: P02

## Context

The project needs a typed API and frontend, durable control metadata, raw object
storage, local ingestion execution, correlated observability, and a maintainable
team-sized architecture. Redis is optional and must have a concrete security-
reviewed use before introduction.

## Decision

- Use Python with FastAPI and strict static typing for the backend API,
  application services, ports, adapters, and local worker.
- Use React with TypeScript strict mode and a small build/test toolchain for the
  frontend.
- Use PostgreSQL for operational/control metadata, lifecycle state, migrations,
  durable ingestion jobs/checkpoints, version registries, and audit metadata.
- Use MinIO for raw source objects and attachments with integrity, provenance,
  quarantine, and lifecycle metadata.
- Use one separate local worker process over the same application use cases and
  ports. PostgreSQL-backed durable job leasing is the initial queue mechanism.
- Use OpenTelemetry for cross-process trace, metric, and log correlation while a
  separate audit port owns durable minimized security events.
- Do not introduce Redis initially. A future measured need and ADR must define
  cache/queue ownership, tenant and policy keys, invalidation, durability, and
  failure behavior.

## Alternatives considered

- Independent microservices per capability: rejected because deployment,
  contracts, and distributed failure modes are unnecessary before measured
  scaling boundaries exist.
- One JavaScript/TypeScript stack: viable, but not selected because the requested
  reference favors Python's model/data ecosystem while retaining strict typed
  API boundaries and a TypeScript frontend.
- Store raw payloads in PostgreSQL: rejected because large immutable objects and
  attachments need object lifecycle and streaming separate from control rows.
- Redis-backed queue/cache from day one: rejected because PostgreSQL already
  supplies required durable control state and there is no measured cache or
  throughput requirement.
- Logs alone for audit: rejected because operational telemetry retention and
  access differ from durable security-event requirements.

## Security and privacy impact

Framework/vendor imports remain in adapters and entrypoints. PostgreSQL rows and
MinIO objects carry tenant/provenance controls but do not replace OpenFGA. The
worker uses least-privilege credentials. OpenTelemetry exporters and audit events
are allowlisted and redacted. Dependency versions and container images require
pinning and lockfiles when implementation begins.

## Evidence and verification

Later checks must enforce import boundaries, strict Python/TypeScript checking,
API contract compatibility, migrations, worker idempotency, job leasing,
MinIO integrity/lifecycle, telemetry redaction/correlation, and absence of Redis
until an accepted use-case ADR exists.

## Consequences

The project remains a modular monolith with one worker and a clear local data
plane. It operates several infrastructure containers but avoids premature service
decomposition and cache/queue infrastructure.
