-- P17: retain minimized query detail and security audit events.

ALTER TABLE query_traces
    ADD COLUMN audit_metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE security_audit_events (
    event_id text PRIMARY KEY CHECK (length(trim(event_id)) > 0),
    event_type text NOT NULL CHECK (event_type IN (
        'LOGIN', 'LOGOUT', 'AUTHZ_DECISION', 'AUTHZ_DENIAL', 'ROLE_CHANGE', 'INGESTION',
        'DELETION', 'POLICY_CHANGE', 'ADMIN_ACTION', 'QUERY'
    )),
    correlation_id text NOT NULL CHECK (length(trim(correlation_id)) > 0),
    trace_id text,
    principal_subject_pseudonym text,
    tenant_id text REFERENCES tenants(tenant_id) ON DELETE RESTRICT,
    outcome text NOT NULL CHECK (outcome IN (
        'ALLOWED', 'DENIED', 'REFUSED', 'FAILED', 'SUCCEEDED'
    )),
    reason_code text NOT NULL CHECK (length(trim(reason_code)) BETWEEN 1 AND 64),
    target_ref_hash char(64),
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    schema_version text NOT NULL CHECK (length(trim(schema_version)) > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX security_audit_events_tenant_time_idx
    ON security_audit_events (tenant_id, created_at DESC);
CREATE INDEX security_audit_events_correlation_idx
    ON security_audit_events (correlation_id);
