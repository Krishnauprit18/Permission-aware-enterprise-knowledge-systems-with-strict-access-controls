# Local Observability

## Enablement

The API and worker composition roots should construct
`create_local_telemetry()` when local OTLP export is desired:

```bash
export KNOWLEDGE_OTEL_ENABLED=1
export KNOWLEDGE_OTEL_GRPC_ENDPOINT=http://127.0.0.1:4317
export KNOWLEDGE_OTEL_SERVICE_NAME=permission-aware-knowledge-backend
```

The default is disabled/no-op. This is an operational setting, not an
authorization setting. A missing or unavailable collector must not widen the
OpenFGA scope or allow protected content to reach the model.

## Local viewer and queries

Start the local platform with `make up`, then use:

- Jaeger trace viewer: `http://127.0.0.1:16686`
- Prometheus query UI: `http://127.0.0.1:9090`
- Collector health: `http://127.0.0.1:13133`
- Collector Prometheus endpoint: `http://127.0.0.1:9464/metrics`

Useful Prometheus queries:

```promql
knowledge_query_completed_total
knowledge_query_failures_total
knowledge_ingestion_completed_total
knowledge_audit_write_failures_total
rate(knowledge_query_failures_total[5m])
```

Metric names may be normalized by the SDK/exporter. Use the Prometheus metric
browser if a name is not present and filter only low-cardinality status/outcome
labels.

## Audit handling

`security_audit_events` is the durable local event table. Query records contain
hashes, IDs, ranks, versions, policy codes, timing, and outcomes; they do not
contain raw questions, source excerpts, credentials, vectors, or model hidden
reasoning. Restrict database access to operators who need audit duties and
apply the retention policy for the local environment.

Authentication and authorization events are emitted with pseudonymous subject
references. Role changes, ingestion, deletion, policy, and administrative
actions use the same typed event boundary and should include a stable hashed
target where relevant. Do not copy event payloads into tickets or chat without
checking tenant and classification policy.

## Failure triage

- No Jaeger spans: verify `KNOWLEDGE_OTEL_ENABLED=1`, collector health, and
  `make platform-status`; then inspect the application process logs for the
  bounded exporter failure counter.
- No audit row: inspect the database migration state and the audit write-failure
  counter. Do not treat missing telemetry as an authorization allow or as proof
  that a query did not execute.
- Unexpected sensitive fields: stop the affected process, preserve only the
  safe event ID/correlation ID, run the P17 redaction tests, and record a
  security finding. Never paste the sensitive payload into logs or issue
  trackers.
