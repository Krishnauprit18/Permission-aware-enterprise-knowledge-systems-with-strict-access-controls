# Embeddings and Search Indexing

## Boundary

P11 consumes P10 `ContentChunk` values and creates disposable OpenSearch
derivatives. It does not authenticate users, resolve OpenFGA scope, perform
query retrieval, rerank, construct evidence, or call an LLM. The frontend has
no OpenSearch credentials or direct search route.

The index is a performance and recall structure, not an authorization source.
Its security fields are defense-in-depth filters and lineage metadata. Later
query code must resolve current authorization through OpenFGA before candidate
text can reach reranking or model context, even when an index field appears to
allow the resource.

## Local embedding contract

`EmbeddingConfig` records model name, immutable model version, dimension,
batch size, text bound, timeout, and retry policy. `EmbeddingProvider` is a
typed application boundary. `ResilientEmbeddingRunner` batches input without
building an unbounded work list, applies timeouts and bounded exponential
retries, and rejects provider model/version/dimension mismatches.

`LocalSemanticEmbeddingProvider` is the runtime adapter. It loads an already
installed FastEmbed ONNX artifact from a local model cache with
`local_files_only=True`, records the configured model identity/version/dimension,
and never sends source text to a hosted provider. `LocalHashEmbeddingProvider`
is retained only as a deterministic unit-test double; it is not a runtime
semantic-quality implementation.

Embeddings contain content-derived features only. Tenant, user, role,
relationship, or external-audience data is never encoded into the vector.
ACL changes therefore do not require re-embedding.

## Index schema

`IndexSchemaConfig` currently defines schema `v1` and an embedding contract.
Physical indexes use immutable names such as
`knowledge-chunks-v1-000001`; the mutable `knowledge-chunks-active` alias is
the only application-facing index reference. Mapping changes, analyzer changes,
or vector dimension/model changes require a new schema or generation.

The explicit mapping uses strict dynamic fields and stores:

- BM25 `text` and a `knn_vector` with the configured dimension;
- chunk/document/version IDs, content hash, ordinal, source type/external ID,
  source URL, author, language, and citation locator strings;
- tenant, account, department, classification, external-share flag, authority,
  created/updated/freshness timestamps, lifecycle status, and ACL relationship
  references;
- embedding model name/version/dimension and index schema version.

The indexed text and vector are derived data. PostgreSQL/MinIO/OpenFGA remain
the authoritative boundaries for lifecycle, raw source, identity, and
authorization. Search derivatives can be deleted and rebuilt from canonical
source revisions.

## Reindex and deletion workflow

1. Select a new positive generation and verify the embedding configuration.
2. Create the immutable physical index with the complete mapping.
3. Parse/normalize/chunk canonical source revisions and embed bounded batches.
4. Bulk-index documents with deterministic chunk IDs and metadata.
5. Reconcile counts and model/schema metadata in the job layer.
6. Atomically move the active alias to the verified generation.
7. Retain or remove the previous generation according to the local operations
   policy; it is never queried through an unversioned fallback.

Deletion or tombstone handling calls the index deletion boundary by chunk or
parent document. A failed delete is an explicit job failure; it is not hidden
by a successful checkpoint. Later deletion orchestration must reconcile every
generation and alias before declaring searchable derivatives removed.

`make reindex-demo` runs the synthetic P09/P10 source boundaries, uses the
offline baseline embedder, and writes to the loopback/private OpenSearch
endpoint configured in the ignored `.env.local`. It prints counts and version
identifiers only; it does not print source text, vectors, credentials, or
OpenSearch response bodies.

## Local network posture

The HTTP adapter rejects public OpenSearch endpoints and accepts loopback,
private IP, or the local Compose service name. The Compose service remains
loopback-bound on the host and private-network-only between containers. TLS
verification follows the local platform configuration; the development demo
certificate posture is not a production deployment claim.
