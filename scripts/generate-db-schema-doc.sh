#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${PLATFORM_ENV_FILE:-$root_dir/.env.local}"
output_file="$root_dir/docs/generated/db-schema.md"

if [[ ! -f "$env_file" ]]; then
  printf '%s\n' "Missing $env_file; run make platform-config first." >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$env_file"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"

psql_local() {
  scripts/compose-local.sh exec -T -e "PGPASSWORD=$POSTGRES_PASSWORD" postgres \
    psql -v ON_ERROR_STOP=1 -X -At -F $'\t' -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"
}

temporary_file="$output_file.tmp.$$"
trap 'rm -f "$temporary_file"' EXIT
mkdir -p "$(dirname "$output_file")"
{
  printf '%s\n' '# Generated PostgreSQL schema'
  printf '%s\n' ''
  printf '%s\n' "Generated from the live \`knowledge\` database by \`scripts/generate-db-schema-doc.sh\`. The migration files under \`backend/migrations/\` are the schema source of truth."
  printf '%s\n' ''
  printf '%s\n' '| Table | Column | PostgreSQL type | Nullable | Default |'
  printf '%s\n' '|---|---|---|---|---|'
  psql_local -c "
    SELECT table_name, column_name, data_type,
           is_nullable, COALESCE(column_default, '')
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name NOT LIKE 'pg_%'
    ORDER BY table_name, ordinal_position
  " | while IFS=$'\t' read -r table column data_type nullable default_value; do
    printf '| %s | %s | %s | %s | %s |\n' \
      "$table" "$column" "$data_type" "$nullable" "$default_value"
  done
} >"$temporary_file"
mv "$temporary_file" "$output_file"
trap - EXIT
printf '%s\n' "Generated $output_file"
