# Generated PostgreSQL schema

Generated from the live `knowledge` database by `scripts/generate-db-schema-doc.sh`. The migration files under `backend/migrations/` are the schema source of truth.

| Table | Column | PostgreSQL type | Nullable | Default |
|---|---|---|---|---|
| accounts | account_id | text | NO |  |
| accounts | tenant_id | text | NO |  |
| accounts | external_id | text | NO |  |
| accounts | name | text | NO |  |
| accounts | status | text | NO | 'ACTIVE'::text |
| accounts | created_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
| accounts | updated_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
| chunks | chunk_id | text | NO |  |
| chunks | document_id | text | NO |  |
| chunks | version_id | text | NO |  |
| chunks | tenant_id | text | NO |  |
| chunks | ordinal | integer | NO |  |
| chunks | content_hash | text | NO |  |
| chunks | search_document_ref | text | NO |  |
| chunks | embedding_model_version | text | YES |  |
| chunks | index_schema_version | text | YES |  |
| chunks | status | text | NO | 'ACTIVE'::text |
| chunks | deleted_at | timestamp with time zone | YES |  |
| chunks | created_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
| deletion_tombstones | tombstone_id | text | NO |  |
| deletion_tombstones | tenant_id | text | NO |  |
| deletion_tombstones | source_type | text | NO |  |
| deletion_tombstones | source_external_id | text | NO |  |
| deletion_tombstones | source_item_id | text | YES |  |
| deletion_tombstones | reason | text | NO |  |
| deletion_tombstones | observed_at | timestamp with time zone | NO |  |
| deletion_tombstones | effective_at | timestamp with time zone | NO |  |
| deletion_tombstones | retention_until | timestamp with time zone | NO |  |
| deletion_tombstones | processed_at | timestamp with time zone | YES |  |
| document_versions | version_id | text | NO |  |
| document_versions | document_id | text | NO |  |
| document_versions | tenant_id | text | NO |  |
| document_versions | version | integer | NO |  |
| document_versions | content_hash | text | NO |  |
| document_versions | raw_object_ref | text | NO |  |
| document_versions | status | text | NO | 'ACTIVE'::text |
| document_versions | supersedes_version_id | text | YES |  |
| document_versions | created_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
| evaluation_cases | case_id | text | NO |  |
| evaluation_cases | dataset_id | text | NO |  |
| evaluation_cases | case_key | text | NO |  |
| evaluation_cases | question | text | NO |  |
| evaluation_cases | expected_evidence_ids | jsonb | NO | '[]'::jsonb |
| evaluation_cases | expected_refusal | boolean | NO |  |
| evaluation_datasets | dataset_id | text | NO |  |
| evaluation_datasets | version | text | NO |  |
| evaluation_datasets | description | text | NO |  |
| evaluation_datasets | created_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
| evaluation_runs | run_id | text | NO |  |
| evaluation_runs | dataset_id | text | NO |  |
| evaluation_runs | status | text | NO |  |
| evaluation_runs | model_versions | jsonb | NO | '{}'::jsonb |
| evaluation_runs | retrieval_metrics | jsonb | NO | '{}'::jsonb |
| evaluation_runs | generation_metrics | jsonb | NO | '{}'::jsonb |
| evaluation_runs | started_at | timestamp with time zone | NO |  |
| evaluation_runs | completed_at | timestamp with time zone | YES |  |
| ingestion_checkpoints | checkpoint_id | text | NO |  |
| ingestion_checkpoints | tenant_id | text | NO |  |
| ingestion_checkpoints | connection_id | text | NO |  |
| ingestion_checkpoints | job_id | text | NO |  |
| ingestion_checkpoints | external_cursor | text | NO |  |
| ingestion_checkpoints | content_hash | text | YES |  |
| ingestion_checkpoints | committed_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
| ingestion_jobs | job_id | text | NO |  |
| ingestion_jobs | tenant_id | text | NO |  |
| ingestion_jobs | connection_id | text | YES |  |
| ingestion_jobs | kind | text | NO |  |
| ingestion_jobs | idempotency_key | text | NO |  |
| ingestion_jobs | status | text | NO | 'PENDING'::text |
| ingestion_jobs | error_code | text | YES |  |
| ingestion_jobs | started_at | timestamp with time zone | YES |  |
| ingestion_jobs | finished_at | timestamp with time zone | YES |  |
| ingestion_jobs | created_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
| principal_references | subject_id | text | NO |  |
| principal_references | tenant_id | text | NO |  |
| principal_references | display_name | text | YES |  |
| principal_references | status | text | NO | 'ACTIVE'::text |
| principal_references | created_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
| principal_references | updated_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
| query_traces | trace_id | text | NO |  |
| query_traces | tenant_id | text | NO |  |
| query_traces | principal_subject_id | text | NO |  |
| query_traces | correlation_id | text | NO |  |
| query_traces | query_hash | character | NO |  |
| query_traces | authorization_fingerprint | character | NO |  |
| query_traces | schema_version | text | NO |  |
| query_traces | outcome | text | NO |  |
| query_traces | evidence_ids | jsonb | NO | '[]'::jsonb |
| query_traces | latency_ms | integer | YES |  |
| query_traces | audit_metadata | jsonb | NO | '{}'::jsonb |
| query_traces | created_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
| query_traces | retention_until | timestamp with time zone | NO |  |
| schema_migrations | migration_version | text | NO |  |
| schema_migrations | checksum_sha256 | character | NO |  |
| schema_migrations | applied_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
| source_connections | connection_id | text | NO |  |
| source_connections | tenant_id | text | NO |  |
| source_connections | source_type | text | NO |  |
| source_connections | external_id | text | NO |  |
| source_connections | base_url | text | YES |  |
| source_connections | credentials_ref | text | YES |  |
| source_connections | status | text | NO | 'ACTIVE'::text |
| source_connections | retention_days | integer | YES |  |
| source_connections | created_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
| source_connections | updated_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
| source_item_accounts | document_id | text | NO |  |
| source_item_accounts | tenant_id | text | NO |  |
| source_item_accounts | account_id | text | NO |  |
| source_items | document_id | text | NO |  |
| source_items | connection_id | text | NO |  |
| source_items | tenant_id | text | NO |  |
| source_items | source_type | text | NO |  |
| source_items | source_external_id | text | NO |  |
| source_items | source_url | text | YES |  |
| source_items | department | text | YES |  |
| source_items | author | text | YES |  |
| source_items | classification | text | NO |  |
| source_items | external_shareable | boolean | NO | false |
| source_items | authority_level | integer | NO |  |
| source_items | acl_relationship_refs | jsonb | NO | '[]'::jsonb |
| source_items | version | integer | NO |  |
| source_items | content_hash | text | NO |  |
| source_items | language | text | NO |  |
| source_items | status | text | NO | 'ACTIVE'::text |
| source_items | deleted_at | timestamp with time zone | YES |  |
| source_items | retention_until | timestamp with time zone | YES |  |
| source_items | supersedes_document_id | text | YES |  |
| source_items | lineage | jsonb | NO | '{}'::jsonb |
| source_items | created_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
| source_items | updated_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
| security_audit_events | event_id | text | NO |  |
| security_audit_events | event_type | text | NO |  |
| security_audit_events | correlation_id | text | NO |  |
| security_audit_events | trace_id | text | YES |  |
| security_audit_events | principal_subject_pseudonym | text | YES |  |
| security_audit_events | tenant_id | text | YES |  |
| security_audit_events | outcome | text | NO |  |
| security_audit_events | reason_code | text | NO |  |
| security_audit_events | target_ref_hash | character | YES |  |
| security_audit_events | attributes | jsonb | NO | '{}'::jsonb |
| security_audit_events | schema_version | text | NO |  |
| security_audit_events | created_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
| tenants | tenant_id | text | NO |  |
| tenants | name | text | NO |  |
| tenants | status | text | NO | 'ACTIVE'::text |
| tenants | created_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
| tenants | updated_at | timestamp with time zone | NO | CURRENT_TIMESTAMP |
