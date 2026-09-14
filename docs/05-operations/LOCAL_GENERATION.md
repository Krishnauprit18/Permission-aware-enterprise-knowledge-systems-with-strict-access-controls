# Local Grounded Generation

P14 uses `LocalOllamaGenerationAdapter`, a local-only Ollama-compatible HTTP
client. It does not start a model runtime, pull a model, or store model
artifacts in the repository. Operators must provision and verify a local runtime
before enabling an answer composition root.

## Configuration

All values are non-secret local configuration. The adapter rejects non-loopback
URLs and URL credentials.

| Variable | Default | Meaning |
|---|---|---|
| `LOCAL_LLM_ENDPOINT` | `http://127.0.0.1:11434/api/chat` | Local runtime chat endpoint |
| `LOCAL_LLM_MODEL` | `qwen2.5:3b-instruct-q4_K_M` | Locally installed model name |
| `LOCAL_LLM_MODEL_VERSION` | `operator-managed-local` | Reviewed local artifact/version label |
| `LOCAL_LLM_TIMEOUT_MS` | `8000` | Per-generation timeout, 100 to 60000 ms |
| `LOCAL_LLM_MAX_OUTPUT_TOKENS` | `512` | Output limit, 32 to 2048 tokens |
| `LOCAL_LLM_MAX_CONCURRENCY` | `1` | In-process generation limit, 1 to 8 |

The model name/version belongs in operator change evidence. Model artifacts
remain local/on-prem data; default application code does not call a cloud
inference API.

## Safety Behavior

- The adapter sends no `tools` field and does not implement function calling.
- Only a P14 authorized context can reach the adapter.
- Source data is a delimited untrusted JSON message, never a trusted prompt.
- Malformed runtime output, timeout, transport failure, and concurrency
  exhaustion produce a generic unavailable answer without response-body logging.
- A fabricated ID or quote is retried once, then becomes a generic refusal.

## Verification

```bash
UV_CACHE_DIR=/tmp/p14-uv-cache uv run --directory backend pytest \
  tests/unit/test_grounded_generation.py \
  tests/unit/test_local_generation_adapter.py -q --no-cov
```

Use `make verify` for the full fast repository gate. A future operator-run
live-model acceptance test must prove the selected local artifact honors the
JSON contract and bounds without sending source content outside the host.
