#!/usr/bin/env bash
set -euo pipefail

env_file="${PLATFORM_ENV_FILE:-.env.local}"
keycloak_url="${KEYCLOAK_URL:-http://127.0.0.1:8080}"
realm="knowledge-local"
network_name="${COMPOSE_PROJECT_NAME:-permission-aware-knowledge}_platform"
curl_image='curlimages/curl:8.10.1@sha256:fcff5cf7a4b895da7bd2933c914938db2b05d2113fa0d6c55b6d29930408f661'

if [[ ! -f "$env_file" ]]; then
  printf '%s\n' "Missing $env_file; run make platform-config first." >&2
  exit 1
fi

command -v curl >/dev/null || { printf '%s\n' 'curl is required.' >&2; exit 1; }
command -v jq >/dev/null || { printf '%s\n' 'jq is required.' >&2; exit 1; }
command -v openssl >/dev/null || { printf '%s\n' 'openssl is required.' >&2; exit 1; }

set -a
# shellcheck disable=SC1090
source "$env_file"
set +a

ensure_password() {
  local variable_name="$1"
  if ! grep -q "^${variable_name}=" "$env_file"; then
    printf '%s=%s\n' "$variable_name" "Kx9!$(openssl rand -hex 20)" >>"$env_file"
  fi
}

ensure_password DEMO_ALICE_PASSWORD
ensure_password DEMO_PRIYA_PASSWORD
ensure_password DEMO_MIGUEL_PASSWORD
ensure_password DEMO_LEAH_PASSWORD
ensure_password DEMO_DANI_PASSWORD
chmod 600 "$env_file"

# Re-read generated demo credentials without printing them.
set -a
# shellcheck disable=SC1090
source "$env_file"
set +a

network_curl() {
  docker run --rm --network "$network_name" "$curl_image" "$@"
}

request_keycloak() {
  local host_url="$1"
  local network_url="$2"
  shift 2
  if ! curl --fail --silent --show-error --max-time 10 "$@" "$host_url"; then
    network_curl --fail --silent --show-error --max-time 10 "$@" "$network_url"
  fi
}

admin_token="$(request_keycloak \
  "$keycloak_url/realms/master/protocol/openid-connect/token" \
  'http://keycloak:8080/realms/master/protocol/openid-connect/token' \
  --data-urlencode "username=$KEYCLOAK_ADMIN_USERNAME" \
  --data-urlencode "password=$KEYCLOAK_ADMIN_PASSWORD" \
  --data-urlencode 'grant_type=password' \
  --data-urlencode 'client_id=admin-cli' \
  | jq -er '.access_token')"

create_or_update_user() {
  local username="$1"
  local password="$2"
  local user_id
  local payload
  user_id="$(request_keycloak \
    "$keycloak_url/admin/realms/$realm/users?username=$(printf '%s' "$username" | jq -sRr @uri)" \
    "http://keycloak:8080/admin/realms/$realm/users?username=$(printf '%s' "$username" | jq -sRr @uri)" \
    -H "Authorization: Bearer $admin_token" \
    | jq -r '.[0].id // ""')"
  payload="$(jq -cn --arg password "$password" '{type:"password",value:$password,temporary:false}')"
  if [[ -n "$user_id" ]]; then
    request_keycloak \
      "$keycloak_url/admin/realms/$realm/users/$user_id/reset-password" \
      "http://keycloak:8080/admin/realms/$realm/users/$user_id/reset-password" \
      -X PUT \
      -H "Authorization: Bearer $admin_token" \
      -H 'Content-Type: application/json' \
      -d "$payload" >/dev/null
  else
    printf '%s\n' "Expected imported user $username was not found in realm $realm." >&2
    exit 1
  fi
}

create_or_update_user alice.account-manager "$DEMO_ALICE_PASSWORD"
create_or_update_user priya.product-manager "$DEMO_PRIYA_PASSWORD"
create_or_update_user miguel.support-engineer "$DEMO_MIGUEL_PASSWORD"
create_or_update_user leah.legal-counsel "$DEMO_LEAH_PASSWORD"
create_or_update_user dani.finance "$DEMO_DANI_PASSWORD"

printf '%s\n' "Keycloak demo users are ready; generated credentials remain only in $env_file"
