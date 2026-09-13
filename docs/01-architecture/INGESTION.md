# Connector and Ingestion Boundary

## P09 implementation boundary

P09 accepts source changes and safely hands them to canonical persistence and
authorization ports. It stops before parsing, body normalization, chunking,
embedding, OpenSearch indexing, retrieval, reranking, and model generation.
This makes the raw-source trust boundary testable before text becomes a
searchable derivative.

## Connector contract

`knowledge_system.application.ports.ingestion.Connector` exposes a source type
and `iter_changes(checkpoint)`. Each result is either a `SourceEnvelope` or a
safe `ConnectorFailure`. An envelope contains stable document and source
identity, tenant metadata, version, timestamps, classification, ACL references,
content hash, ordered source cursor, deletion state, content type, raw bytes
when available, bounded attachment references/content, and optional lineage.

Connector code is an adapter, not an authorization decision maker. Source ACL
records can only create typed `AclRelationshipIntent` values; the OpenFGA
write/check adapter remains the policy boundary. Source body text is never
interpreted as policy.

## Fixture trust boundary

`FixtureCatalog` reads only manifest-selected files beneath a configured,
resolved fixture root. It rejects path traversal, non-regular files, unknown
suffixes, empty files, files over the configured byte limit, malformed JSON,
source-type mismatches, duplicate `(tenant, source type, external ID)`
identities, missing ACL mappings, UTC timestamp violations, and manifest hash
mismatches. It does not follow arbitrary URLs or fetch attachment references.

The fixture root is trusted configuration; its manifest, ACL file, filenames,
metadata, JSON fields, and source bytes are untrusted data. `source_path` is
retained only as internal provenance and is never written to logs. The default
limit is 1 MiB per source file. Later parsers and attachment handlers require
their own independent limits and quarantine policy.

| Connector | Source type | Accepted fixture form |
|---|---|---|
| `FilesystemFixtureConnector` | `document` | bounded Markdown-like files |
| `SupportTicketFixtureConnector` | `support_ticket` | bounded JSON objects |
| `SlackFixtureConnector` | `slack_thread` | bounded JSON objects |
| `CallTranscriptFixtureConnector` | `call_transcript` | bounded JSON objects |

## Orchestration order

For each source change, `IngestionOrchestrator` performs this order:

1. Validate connection and envelope tenant identity.
2. Detect an unchanged, already checkpointed revision by content hash, version,
   and lifecycle status.
3. For an active item, store raw bytes in `RawObjectStore` first. The MinIO
   adapter writes a generated tenant/source/document/version/hash key with
   allowlisted provenance metadata. Attachment bytes are separately keyed;
   external attachment references are not fetched by P09.
4. Persist `SourceItem` and, for active items, `DocumentVersion` through one
   explicit PostgreSQL transaction.
5. Apply or remove ACL relationship intents through the dedicated sink. The
   connector does not call OpenFGA directly.
6. Persist deletion tombstones for deleted items.
7. Persist the source cursor only after preceding operations succeed.

PostgreSQL, object-store, and OpenFGA boundaries cannot share one local
transaction. Ordering, idempotent IDs, tombstones, and replay behavior are the
consistency contract. A failure before a checkpoint leaves the item eligible
for replay. Later items may be processed, but the returned cursor never
advances across a failure gap.

## Retry and failure policy

Raw-object writes retry only typed `TransientIngestionError` failures, using a
bounded exponential delay and fixed maximum attempts. Permanent input or key
errors are never retried. Exhausted retries become safe item failures. Each
item is isolated so unrelated changes can proceed. Connector and item failures
use stable error codes in structured logs and job status; raw exception text is
not emitted. A connector iterator failure finalizes the job as failed and is
re-raised. Base exceptions such as interruption are allowed to leave a running
job recoverable without recording a successful checkpoint.

## Future handoff

Later stages consume the raw reference and canonical metadata while preserving
document/version lineage and the deletion and authorization ordering. No
downstream adapter may treat an ACL intent, search filter, or source body field
as an allow decision without the P06 authorization service.
