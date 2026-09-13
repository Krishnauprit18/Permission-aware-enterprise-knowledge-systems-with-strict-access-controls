#!/usr/bin/env bash
set -euo pipefail

env_file="${PLATFORM_ENV_FILE:-.env.local}"
# The file is generated locally or explicitly supplied by the operator.
# shellcheck disable=SC1090
source "$env_file"

network_name="${COMPOSE_PROJECT_NAME:-permission-aware-knowledge}_platform"
curl_image='curlimages/curl:8.10.1@sha256:fcff5cf7a4b895da7bd2933c914938db2b05d2113fa0d6c55b6d29930408f661'

network_curl() {
  docker run --rm --network "$network_name" "$curl_image" "$@"
}

check_http() {
  local name="$1"
  local host_url="$2"
  local network_url="$3"
  if ! curl -fsS --max-time 5 "$host_url" -o /dev/null 2>/dev/null; then
    network_curl -fsS --max-time 5 "$network_url" -o /dev/null
  fi
  printf '%s\n' "ok: $name"
}

scripts/compose-local.sh exec -T postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null
printf '%s\n' 'ok: postgres readiness'

if ! curl -fsS -k --max-time 5 -u "admin:${OPENSEARCH_INITIAL_ADMIN_PASSWORD}" \
  'https://127.0.0.1:9200/_cluster/health?wait_for_status=yellow' -o /dev/null 2>/dev/null; then
  network_curl -fsS -k --max-time 5 -u "admin:${OPENSEARCH_INITIAL_ADMIN_PASSWORD}" \
    'https://opensearch:9200/_cluster/health?wait_for_status=yellow' -o /dev/null
fi
printf '%s\n' 'ok: opensearch health'

response_file="$(mktemp)"
trap 'rm -f "$response_file"' EXIT
if ! curl -fsS -k --max-time 5 -u "admin:${OPENSEARCH_INITIAL_ADMIN_PASSWORD}" \
  'https://127.0.0.1:9200/' -o "$response_file" 2>/dev/null; then
  network_curl -fsS -k --max-time 5 -u "admin:${OPENSEARCH_INITIAL_ADMIN_PASSWORD}" \
    'https://opensearch:9200/' > "$response_file"
fi
grep -q '"version"' "$response_file"
printf '%s\n' 'ok: opensearch version endpoint'

check_http 'keycloak readiness' 'http://127.0.0.1:9100/health/ready' 'http://keycloak:9000/health/ready'
check_http 'keycloak master realm' 'http://127.0.0.1:8080/realms/master' 'http://keycloak:8080/realms/master'
check_http 'openfga health' 'http://127.0.0.1:8081/healthz' 'http://openfga:8080/healthz'
check_http 'minio liveness' 'http://127.0.0.1:9000/minio/health/live' 'http://minio:9000/minio/health/live'
check_http 'otel collector health' 'http://127.0.0.1:13133/' 'http://otel-collector:13133/'
check_http 'jaeger trace viewer' 'http://127.0.0.1:16686/' 'http://jaeger:16686/'
check_http 'prometheus readiness' 'http://127.0.0.1:9090/-/ready' 'http://prometheus:9090/-/ready'
