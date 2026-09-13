#!/usr/bin/env bash
set -euo pipefail

env_file="${PLATFORM_ENV_FILE:-.env.local}"
compose_file="${COMPOSE_FILE:-compose.yml}"

exec docker compose --env-file "$env_file" --file "$compose_file" "$@"
