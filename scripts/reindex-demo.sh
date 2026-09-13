#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f "${PLATFORM_ENV_FILE:-.env.local}" ]]; then
  printf '%s\n' 'Missing local platform environment; run make bootstrap-platform first.' >&2
  exit 1
fi

exec uv run --directory backend python -m knowledge_system.indexing.reindex_demo
