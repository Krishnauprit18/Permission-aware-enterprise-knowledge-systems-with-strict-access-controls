# Local Search Index Operations

## Rebuild

Start the private platform and ensure `.env.local` exists, then run:

```text
make up
make reindex-demo
```

The command creates `knowledge-chunks-v1-000001` by default and moves
`knowledge-chunks-active` after successful bulk indexing. Use
`INDEX_GENERATION=N` for a new immutable generation. The local baseline
embedder is deterministic and offline; no source content is sent to a cloud
service.

The command is an indexing operation, not a query demo. There is no browser
route to OpenSearch, and the index does not authorize access. Current OpenFGA
decisions remain mandatory for later retrieval.

## Configuration

Optional local variables are read from the ignored `.env.local` or the process
environment:

| Variable | Default | Meaning |
|---|---|---|
| `OPENSEARCH_URL` | `https://127.0.0.1:9200` | Loopback/private endpoint only |
| `OPENSEARCH_USERNAME` | `admin` | Local service identity |
| `EMBEDDING_MODEL_NAME` | `local-hash-embedding` | Configured local adapter name |
| `EMBEDDING_MODEL_VERSION` | `1` | Immutable adapter/model version |
| `EMBEDDING_DIMENSION` | `384` | Vector dimension and mapping contract |
| `EMBEDDING_BATCH_SIZE` | `16` | Bounded batch size |
| `INDEX_GENERATION` | `1` | Immutable physical index generation |

Passwords are read from the generated local environment and are never printed
or committed. Do not put model artifacts, source text, or vectors in logs.

## Failure and recovery

- A model/version/dimension mismatch stops indexing before alias activation.
- A timeout or transient embedding failure retries within the configured bound;
  exhausted retries fail the operation without a partial success claim.
- OpenSearch errors expose only method/path/status to the application error;
  response bodies are not logged or returned.
- A failed generation can be discarded and rebuilt. The previous alias remains
  the last verified generation until cutover.
- Deletion jobs must call the index deletion boundary and reconcile all active
  generations before completion. Removing a PostgreSQL row alone does not
  remove a searchable derivative.

The OpenSearch named volume is operational local data. Back it up only with a
version-compatible OpenSearch procedure; the canonical source revisions remain
the rebuild authority.
