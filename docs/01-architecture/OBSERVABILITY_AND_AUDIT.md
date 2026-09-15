# Observability And Audit

## Boundary

P17 separates operational telemetry from the security audit record. OpenTelemetry
spans and metrics help an operator debug latency and dependency behavior; they
are not an authorization source and do not replace durable audit events.

The application emits content-free spans through `TelemetryPort`. The default
implementation is a no-op, which keeps offline unit work and protected requests
independent of collector availability. `OpenTelemetryAdapter` exports OTLP
traces and metrics to the local collector when `KNOWLEDGE_OTEL_ENABLED=1`.

## Query audit contract

`QueryAuditRecord` captures:

- request/correlation ID and a stable pseudonymous subject reference;
- tenant and authorization model, tuple, policy, scope, and fingerprint values;
- query hash, normalized length, and term count, never the raw question;
- BM25/vector candidate IDs, component ranks/scores, fused and rerank ranks;
- evidence IDs sent to the model and document-version IDs;
- prompt template/model identifiers, citation-validation outcome, policy warning
  codes, context size, optional token counts, latency by stage, and final outcome;
- a bounded error class when the protected pipeline fails.

The record contains no source text, full prompt, bearer token, cookie, secret,
embedding vector, or hidden model reasoning. `PostgresAuditSink` stores the
record as a `QUERY` event in `security_audit_events` using the JSON metadata
payload. The existing `query_traces` table remains the compact compatibility
record and now has an `audit_metadata` extension field.

## Security events

`SecurityAuditEvent` is restricted to an allowlisted category: `LOGIN`, `LOGOUT`,
`AUTHZ_DECISION`, `AUTHZ_DENIAL`, `ROLE_CHANGE`, `INGESTION`, `DELETION`,
`POLICY_CHANGE`, `ADMIN_ACTION`, or `QUERY`. Targets are represented by hashes
when an event needs a target reference. The authorization bridge records safe
OpenFGA decision metadata without relationship graph dumps.

Authentication, query, and ingestion audit write failures are observable and do
not grant access, widen search scope, or change a protected answer. The core
operation continues with its existing security behavior while a failure counter
and safe diagnostic are emitted. Security-event payloads must remain minimized;
an operator must not treat best-effort telemetry as proof that an event was
durably stored.

## Span map

The protected query path emits nested spans:

```text
http.knowledge.query
  knowledge.query
    knowledge.query.retrieval
    knowledge.query.evidence
    knowledge.query.generation
```

The ingestion orchestrator emits `knowledge.ingestion.sync` with source type,
tenant, and connection metadata only. Connector item text, attachments, and
raw paths are never span attributes. Correlation IDs are attached as attributes
and carried by the OTel current-context mechanism.

## Metrics

The local adapter records bounded counters for query completion/failure,
ingestion completion/failure, and audit write/log failures. Metric attributes
are low-cardinality values such as outcome and status; user IDs, question text,
resource lists, and evidence text are excluded.
