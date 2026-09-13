#!/usr/bin/env bash
set -euo pipefail

env_file="${PLATFORM_ENV_FILE:-.env.local}"

if [[ -f "$env_file" ]]; then
  chmod 600 "$env_file"
  if [[ "${PLATFORM_ROTATE_OPENSEARCH_PASSWORD:-0}" == "1" ]]; then
    umask 077
    temporary_file="${env_file}.tmp.$$"
    trap 'rm -f "$temporary_file"' EXIT
    awk -v password="Kx9!$(openssl rand -hex 20)" \
      'BEGIN { updated = 0 } \
       /^OPENSEARCH_INITIAL_ADMIN_PASSWORD=/ { print "OPENSEARCH_INITIAL_ADMIN_PASSWORD=" password; updated = 1; next } \
       { print } \
       END { if (!updated) print "OPENSEARCH_INITIAL_ADMIN_PASSWORD=" password }' \
      "$env_file" > "$temporary_file"
    mv "$temporary_file" "$env_file"
    trap - EXIT
    printf '%s\n' "Rotated the local OpenSearch administrator password in $env_file"
  fi
  exit 0
fi

umask 077
temporary_file="${env_file}.tmp.$$"
trap 'rm -f "$temporary_file"' EXIT

random_secret() {
  openssl rand -hex 24
}

random_password() {
  printf 'Kx9!%s\n' "$(openssl rand -hex 20)"
}

{
  printf '%s\n' "# Generated local-only platform credentials. Never commit this file."
  printf 'POSTGRES_USER=knowledge_platform\n'
  printf 'POSTGRES_PASSWORD=%s\n' "$(random_secret)"
  printf 'POSTGRES_DB=knowledge\n'
  printf 'KEYCLOAK_ADMIN_USERNAME=local-admin\n'
  printf 'KEYCLOAK_ADMIN_PASSWORD=%s\n' "$(random_secret)"
  printf 'OPENSEARCH_INITIAL_ADMIN_PASSWORD=%s\n' "$(random_password)"
  printf 'MINIO_ROOT_USER=minio_local_admin\n'
  printf 'MINIO_ROOT_PASSWORD=%s\n' "$(random_secret)"
} > "$temporary_file"

mv "$temporary_file" "$env_file"
trap - EXIT
printf '%s\n' "Created local platform environment at $env_file"
