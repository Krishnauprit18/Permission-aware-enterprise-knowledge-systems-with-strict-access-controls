# ADR-019: Content-Free Observability And Durable Audit

- Status: accepted
- Date: 2026-09-15
- Scope: P17 auditability and observability

## Context

The system needs query reconstruction, security-event accountability, and local
latency debugging without turning logs or traces into a second source of
confidential content. Authorization and policy decisions must remain correct if
the collector or audit transport is unavailable.

## Decision

Use a typed `QueryAuditRecord` and `SecurityAuditEvent` boundary. Persist
minimized security events in PostgreSQL through `PostgresAuditSink`; keep user
subjects pseudonymous and target references hashed when a stable target binding
is useful. Keep raw query text, source text, prompts, tokens, vectors, bearer
credentials, cookies, and hidden model reasoning out of operational logs and
audit payloads.

Instrument application-owned query and ingestion stages through a small
framework-neutral telemetry port. Use the OpenTelemetry SDK and OTLP gRPC
exporter to the existing local collector, Jaeger, and Prometheus path when
explicitly enabled. The default is no-op telemetry so collector failure cannot
grant access or make protected authorization depend on an external process.

Authentication, authorization, lifecycle, policy, and administrative code may
emit the same allowlisted event type set. Audit writes are best effort for the
current local product boundary: write failures produce a bounded failure metric
and safe diagnostic, while the protected operation keeps its existing deny or
allow decision. A future deployment requiring mandatory audit durability must
replace this policy with a durable queue or fail-closed event writer and add
acceptance evidence before activation.

## Alternatives considered

- **Log complete requests and responses:** rejected because it creates a
  searchable confidentiality copy and can retain secrets or prompt-injection
  payloads.
- **Use OpenTelemetry as the audit database:** rejected because operational
  retention, sampling, and collector availability are not security-accounting
  guarantees.
- **Make every query fail when telemetry is unavailable:** rejected for the
  current local boundary because it couples availability to a non-authoritative
  diagnostic path; protected authorization still fails closed independently.
- **Use an LLM to summarize or classify audit events:** rejected because audit
  categories and security decisions must be deterministic and model-independent.

## Verification

Unit tests assert redaction of tokens, cookies, raw text, vectors, and arbitrary
sensitive keys; stable pseudonymous subjects; safe denied-authorization events;
trace nesting/correlation; and audit outage behavior. Integration tests apply
the P17 migration and persist an event when PostgreSQL is available. This ADR
defines alignment and verification guidance only; it makes no certification or
compliance claim.
