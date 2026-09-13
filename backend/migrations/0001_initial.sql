-- Canonical control metadata. Searchable text and embeddings remain in OpenSearch.
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_version text PRIMARY KEY,
    checksum_sha256 char(64) NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tenants (
    tenant_id text PRIMARY KEY CHECK (length(trim(tenant_id)) > 0),
    name text NOT NULL CHECK (length(trim(name)) > 0),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DELETED')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE principal_references (
    subject_id text PRIMARY KEY CHECK (length(trim(subject_id)) > 0),
    tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE RESTRICT,
    display_name text,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DELETED')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE accounts (
    account_id text PRIMARY KEY CHECK (length(trim(account_id)) > 0),
    tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE RESTRICT,
    external_id text NOT NULL CHECK (length(trim(external_id)) > 0),
    name text NOT NULL CHECK (length(trim(name)) > 0),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DELETED')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, external_id),
    UNIQUE (account_id, tenant_id)
);

CREATE TABLE source_connections (
    connection_id text PRIMARY KEY CHECK (length(trim(connection_id)) > 0),
    tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE RESTRICT,
    source_type text NOT NULL CHECK (length(trim(source_type)) > 0),
    external_id text NOT NULL CHECK (length(trim(external_id)) > 0),
    base_url text,
    credentials_ref text,
    status text NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'PAUSED', 'DISABLED')),
    retention_days integer CHECK (retention_days IS NULL OR retention_days > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, source_type, external_id),
    UNIQUE (connection_id, tenant_id)
);

CREATE TABLE source_items (
    document_id text PRIMARY KEY CHECK (length(trim(document_id)) > 0),
    connection_id text NOT NULL,
    tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE RESTRICT,
    source_type text NOT NULL CHECK (length(trim(source_type)) > 0),
    source_external_id text NOT NULL CHECK (length(trim(source_external_id)) > 0),
    source_url text,
    department text,
    author text,
    classification text NOT NULL CHECK (
        classification IN ('PUBLIC', 'CUSTOMER_SHAREABLE', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')
    ),
    external_shareable boolean NOT NULL DEFAULT false,
    authority_level integer NOT NULL CHECK (authority_level >= 0),
    acl_relationship_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    version integer NOT NULL CHECK (version > 0),
    content_hash text NOT NULL CHECK (length(trim(content_hash)) > 0),
    language text NOT NULL CHECK (length(trim(language)) > 0),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DELETED')),
    deleted_at timestamptz,
    retention_until timestamptz,
    supersedes_document_id text REFERENCES source_items(document_id) ON DELETE RESTRICT,
    lineage jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (connection_id, tenant_id)
        REFERENCES source_connections(connection_id, tenant_id) ON DELETE RESTRICT,
    UNIQUE (document_id, tenant_id),
    UNIQUE (tenant_id, source_type, source_external_id),
    CHECK ((status = 'DELETED') = (deleted_at IS NOT NULL)),
    CHECK (retention_until IS NULL OR deleted_at IS NOT NULL),
    CHECK (supersedes_document_id IS NULL OR supersedes_document_id <> document_id),
    CHECK (NOT external_shareable OR classification IN ('PUBLIC', 'CUSTOMER_SHAREABLE'))
);

CREATE TABLE source_item_accounts (
    document_id text NOT NULL REFERENCES source_items(document_id) ON DELETE CASCADE,
    tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE RESTRICT,
    account_id text NOT NULL,
    PRIMARY KEY (document_id, account_id),
    FOREIGN KEY (document_id, tenant_id)
        REFERENCES source_items(document_id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (account_id, tenant_id)
        REFERENCES accounts(account_id, tenant_id) ON DELETE RESTRICT
);

CREATE TABLE document_versions (
    version_id text PRIMARY KEY CHECK (length(trim(version_id)) > 0),
    document_id text NOT NULL,
    tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE RESTRICT,
    version integer NOT NULL CHECK (version > 0),
    content_hash text NOT NULL CHECK (length(trim(content_hash)) > 0),
    raw_object_ref text NOT NULL CHECK (length(trim(raw_object_ref)) > 0),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DELETED')),
    supersedes_version_id text REFERENCES document_versions(version_id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (document_id, tenant_id, version),
    UNIQUE (version_id, document_id, tenant_id),
    FOREIGN KEY (document_id, tenant_id)
        REFERENCES source_items(document_id, tenant_id) ON DELETE RESTRICT,
    CHECK (supersedes_version_id IS NULL OR supersedes_version_id <> version_id)
);

CREATE TABLE chunks (
    chunk_id text PRIMARY KEY CHECK (length(trim(chunk_id)) > 0),
    document_id text NOT NULL,
    version_id text NOT NULL,
    tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE RESTRICT,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    content_hash text NOT NULL CHECK (length(trim(content_hash)) > 0),
    search_document_ref text NOT NULL CHECK (length(trim(search_document_ref)) > 0),
    embedding_model_version text,
    index_schema_version text,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DELETED')),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (document_id, version_id, ordinal),
    FOREIGN KEY (version_id, document_id, tenant_id)
        REFERENCES document_versions(version_id, document_id, tenant_id) ON DELETE RESTRICT,
    CHECK ((status = 'DELETED') = (deleted_at IS NOT NULL))
);

CREATE TABLE ingestion_jobs (
    job_id text PRIMARY KEY CHECK (length(trim(job_id)) > 0),
    tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE RESTRICT,
    connection_id text,
    kind text NOT NULL CHECK (length(trim(kind)) > 0),
    idempotency_key text NOT NULL CHECK (length(trim(idempotency_key)) > 0),
    status text NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    error_code text,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (connection_id, tenant_id)
        REFERENCES source_connections(connection_id, tenant_id) ON DELETE RESTRICT
);

CREATE TABLE ingestion_checkpoints (
    checkpoint_id text PRIMARY KEY CHECK (length(trim(checkpoint_id)) > 0),
    tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE RESTRICT,
    connection_id text NOT NULL,
    job_id text NOT NULL REFERENCES ingestion_jobs(job_id) ON DELETE RESTRICT,
    external_cursor text NOT NULL CHECK (length(trim(external_cursor)) > 0),
    content_hash text,
    committed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (connection_id, external_cursor),
    FOREIGN KEY (connection_id, tenant_id)
        REFERENCES source_connections(connection_id, tenant_id) ON DELETE RESTRICT
);

CREATE TABLE deletion_tombstones (
    tombstone_id text PRIMARY KEY CHECK (length(trim(tombstone_id)) > 0),
    tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE RESTRICT,
    source_type text NOT NULL CHECK (length(trim(source_type)) > 0),
    source_external_id text NOT NULL CHECK (length(trim(source_external_id)) > 0),
    source_item_id text REFERENCES source_items(document_id) ON DELETE RESTRICT,
    reason text NOT NULL CHECK (length(trim(reason)) > 0),
    observed_at timestamptz NOT NULL,
    effective_at timestamptz NOT NULL,
    retention_until timestamptz NOT NULL,
    processed_at timestamptz,
    UNIQUE (tenant_id, source_type, source_external_id),
    CHECK (retention_until >= effective_at)
);

CREATE TABLE query_traces (
    trace_id text PRIMARY KEY CHECK (length(trim(trace_id)) > 0),
    tenant_id text NOT NULL REFERENCES tenants(tenant_id) ON DELETE RESTRICT,
    principal_subject_id text NOT NULL REFERENCES principal_references(subject_id) ON DELETE RESTRICT,
    correlation_id text NOT NULL CHECK (length(trim(correlation_id)) > 0),
    query_hash char(64) NOT NULL,
    authorization_fingerprint char(64) NOT NULL,
    schema_version text NOT NULL CHECK (length(trim(schema_version)) > 0),
    outcome text NOT NULL CHECK (outcome IN ('ANSWERED', 'REFUSED', 'FAILED')),
    evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    latency_ms integer CHECK (latency_ms IS NULL OR latency_ms >= 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    retention_until timestamptz NOT NULL
);

CREATE TABLE evaluation_datasets (
    dataset_id text PRIMARY KEY CHECK (length(trim(dataset_id)) > 0),
    version text NOT NULL CHECK (length(trim(version)) > 0),
    description text NOT NULL CHECK (length(trim(description)) > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (version)
);

CREATE TABLE evaluation_cases (
    case_id text PRIMARY KEY CHECK (length(trim(case_id)) > 0),
    dataset_id text NOT NULL REFERENCES evaluation_datasets(dataset_id) ON DELETE CASCADE,
    case_key text NOT NULL CHECK (length(trim(case_key)) > 0),
    question text NOT NULL CHECK (length(trim(question)) > 0),
    expected_evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    expected_refusal boolean NOT NULL,
    UNIQUE (dataset_id, case_key)
);

CREATE TABLE evaluation_runs (
    run_id text PRIMARY KEY CHECK (length(trim(run_id)) > 0),
    dataset_id text NOT NULL REFERENCES evaluation_datasets(dataset_id) ON DELETE RESTRICT,
    status text NOT NULL CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    model_versions jsonb NOT NULL DEFAULT '{}'::jsonb,
    retrieval_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    generation_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz NOT NULL,
    completed_at timestamptz
);

CREATE INDEX source_items_tenant_status_idx ON source_items (tenant_id, status);
CREATE INDEX source_items_source_lookup_idx
    ON source_items (tenant_id, source_type, source_external_id);
CREATE INDEX source_item_accounts_account_idx ON source_item_accounts (tenant_id, account_id);
CREATE INDEX document_versions_document_idx ON document_versions (tenant_id, document_id, version DESC);
CREATE INDEX chunks_tenant_status_idx ON chunks (tenant_id, status);
CREATE INDEX chunks_version_idx ON chunks (tenant_id, document_id, version_id);
CREATE INDEX ingestion_jobs_status_idx ON ingestion_jobs (tenant_id, status, created_at);
CREATE INDEX ingestion_checkpoints_connection_idx ON ingestion_checkpoints (tenant_id, connection_id, committed_at DESC);
CREATE INDEX deletion_tombstones_pending_idx ON deletion_tombstones (tenant_id, processed_at, effective_at);
CREATE INDEX query_traces_retention_idx ON query_traces (tenant_id, retention_until);
CREATE INDEX evaluation_runs_dataset_idx ON evaluation_runs (dataset_id, started_at DESC);
