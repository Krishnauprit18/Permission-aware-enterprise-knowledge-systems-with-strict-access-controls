#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${PLATFORM_ENV_FILE:-$root_dir/.env.local}"
migrations_dir="$root_dir/backend/migrations"

if [[ ! -f "$env_file" ]]; then
  printf '%s\n' "Missing $env_file; run make platform-config first." >&2
  exit 1
fi
command -v sha256sum >/dev/null || { printf '%s\n' 'sha256sum is required.' >&2; exit 1; }
command -v sort >/dev/null || { printf '%s\n' 'sort is required.' >&2; exit 1; }

# This file is generated locally or explicitly supplied by the operator.
# shellcheck disable=SC1090
source "$env_file"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"

psql_local() {
  scripts/compose-local.sh exec -T -e "PGPASSWORD=$POSTGRES_PASSWORD" postgres \
    psql -v ON_ERROR_STOP=1 -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"
}

psql_local -c "CREATE TABLE IF NOT EXISTS schema_migrations (
  migration_version text PRIMARY KEY,
  checksum_sha256 char(64) NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);" >/dev/null

mapfile -t migration_files < <(find "$migrations_dir" -maxdepth 1 -type f -name '*.sql' -print | sort)
if (( ${#migration_files[@]} == 0 )); then
  printf '%s\n' "No SQL migrations found in $migrations_dir" >&2
  exit 1
fi

for migration_file in "${migration_files[@]}"; do
  migration_version="$(basename "$migration_file" .sql)"
  if [[ ! "$migration_version" =~ ^[0-9]{4}_[a-z0-9_]+$ ]]; then
    printf '%s\n' "Invalid migration filename: $migration_version" >&2
    exit 1
  fi
  checksum="$(sha256sum "$migration_file" | awk '{print $1}')"
  applied_checksum="$(psql_local -Atqc \
    "SELECT checksum_sha256 FROM schema_migrations WHERE migration_version = '$migration_version'")"
  if [[ -n "$applied_checksum" ]]; then
    if [[ "$applied_checksum" != "$checksum" ]]; then
      printf '%s\n' "Migration checksum drift: $migration_version" >&2
      exit 1
    fi
    printf '%s\n' "Already applied: $migration_version"
    continue
  fi

  # The migration and its ledger row share one database transaction.
  {
    printf 'BEGIN;\n'
    cat "$migration_file"
    printf "\nINSERT INTO schema_migrations (migration_version, checksum_sha256) VALUES ('%s', '%s');\n" \
      "$migration_version" "$checksum"
    printf 'COMMIT;\n'
  } | psql_local
  printf '%s\n' "Applied: $migration_version"
done
