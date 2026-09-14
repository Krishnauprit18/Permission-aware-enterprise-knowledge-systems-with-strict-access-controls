# Local Reranker

The P13 semantic reranker uses FastEmbed's local ONNX cross-encoder:
`Xenova/ms-marco-MiniLM-L-6-v2` at revision
`a09144355adeed5f58c8ed011d209bf8ee5a1fec`. The artifact is operator-provided
outside Git; runtime construction uses `local_files_only=True` and cannot
download a model or send source text to a hosted service.

Set the model cache path in the local process configuration, not in source:

```bash
export SEMANTIC_RERANKER_MODEL_PATH=/var/lib/knowledge-system/models
```

The opt-in local acceptance proof is:

```bash
P13_SEMANTIC_RERANKER_LIVE=1 \
SEMANTIC_RERANKER_MODEL_PATH=/var/lib/knowledge-system/models \
UV_CACHE_DIR=/tmp/knowledge-system-uv-cache \
uv run --directory backend --extra semantic \
  pytest tests/integration/test_semantic_reranker_live.py -q --no-cov
```

The command must fail if the artifact is unavailable. It does not fetch model
files and it does not claim a general relevance benchmark.

The paired evidence-store proof requires the already-running local PostgreSQL
and MinIO services and uses a unique schema/object that it removes:

```bash
P13_EVIDENCE_STORE_LIVE=1 \
P13_EVIDENCE_DATABASE_HOST=<private-postgres-host> \
P13_EVIDENCE_MINIO_ENDPOINT=<private-minio-host>:9000 \
UV_CACHE_DIR=/tmp/knowledge-system-uv-cache \
uv run --directory backend \
  pytest tests/integration/test_evidence_store_live.py -q --no-cov
```

Do not expose MinIO, PostgreSQL, model caches, or these test environment values
outside the local trusted runtime boundary.
