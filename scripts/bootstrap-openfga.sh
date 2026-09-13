#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${PLATFORM_ENV_FILE:-$root_dir/.env.local}"
openfga_url="${OPENFGA_URL:-http://127.0.0.1:8081}"
network_name="${COMPOSE_PROJECT_NAME:-permission-aware-knowledge}_platform"
curl_image='curlimages/curl:8.10.1@sha256:fcff5cf7a4b895da7bd2933c914938db2b05d2113fa0d6c55b6d29930408f661'
store_name="permission-aware-knowledge-local"
model_file="$root_dir/platform/openfga/authorization-model.json"
tuple_file="$root_dir/platform/openfga/seed-tuples.json"

if [[ ! -f "$env_file" ]]; then
  printf '%s\n' "Missing $env_file; run make platform-config first." >&2
  exit 1
fi
command -v curl >/dev/null || { printf '%s\n' 'curl is required.' >&2; exit 1; }
command -v jq >/dev/null || { printf '%s\n' 'jq is required.' >&2; exit 1; }

# The file is generated locally or explicitly supplied by the operator.
# shellcheck disable=SC1090
source "$env_file"

network_curl() {
  local method="$1"
  local path="$2"
  local body="$3"
  docker run --rm --network "$network_name" "$curl_image" \
    -fsS --max-time 10 -X "$method" \
    -H 'Content-Type: application/json' \
    --data "$body" "http://openfga:8080$path"
}

request_json() {
  local method="$1"
  local path="$2"
  local body="$3"
  if curl -fsS --silent --show-error --max-time 10 -X "$method" \
    -H 'Content-Type: application/json' --data "$body" \
    "$openfga_url$path" 2>/dev/null; then
    return 0
  fi
  network_curl "$method" "$path" "$body"
}

set_env_value() {
  local name="$1"
  local value="$2"
  local temporary_file="${env_file}.tmp.$$"
  trap 'rm -f "$temporary_file"' EXIT
  awk -v name="$name" -v value="$value" \
    'BEGIN { updated = 0 } \
     $0 ~ "^" name "=" { print name "=" value; updated = 1; next } \
     { print } \
     END { if (!updated) print name "=" value }' \
    "$env_file" > "$temporary_file"
  mv "$temporary_file" "$env_file"
  trap - EXIT
}

stores_response="$(request_json GET "/stores?name=$store_name" '{}')"
store_id="$(jq -r --arg name "$store_name" \
  'first(.stores[] | select(.name == $name) | .id) // ""' <<<"$stores_response")"
if [[ -z "$store_id" ]]; then
  store_id="$(request_json POST /stores "$(jq -cn --arg name "$store_name" '{name:$name}')" \
    | jq -er '.id')"
fi
set_env_value OPENFGA_STORE_ID "$store_id"

models_response="$(request_json GET "/stores/$store_id/authorization-models" '{}')"
model_id="$(jq -r '.authorization_models[0].id // ""' <<<"$models_response")"
if [[ -z "$model_id" ]]; then
  model_payload="$(jq -c . "$model_file")"
  model_id="$(request_json POST "/stores/$store_id/authorization-models" "$model_payload" \
    | jq -er '.authorization_model_id')"
fi
set_env_value OPENFGA_AUTHORIZATION_MODEL_ID "$model_id"

missing='[]'
while IFS= read -r tuple; do
  user="$(jq -er '.user' <<<"$tuple")"
  relation="$(jq -er '.relation' <<<"$tuple")"
  object="$(jq -er '.object' <<<"$tuple")"
  read_payload="$(jq -cn --arg user "$user" --arg relation "$relation" \
    --arg object "$object" '{tuple_key:{user:$user,relation:$relation,object:$object}}')"
  existing="$(request_json POST "/stores/$store_id/read" "$read_payload")"
  if [[ "$(jq -er '.tuples | length' <<<"$existing")" == "0" ]]; then
    missing="$(jq --argjson tuple "$tuple" '. + [$tuple]' <<<"$missing")"
  fi
done < <(jq -c '.[]' "$tuple_file")

if [[ "$(jq -er 'length' <<<"$missing")" != "0" ]]; then
  write_payload="$(jq -cn --argjson tuples "$missing" '{writes:{tuple_keys:$tuples}}')"
  request_json POST "/stores/$store_id/write" "$write_payload" >/dev/null
fi

chmod 600 "$env_file"
printf '%s\n' "OpenFGA model and synthetic tuples are ready in store $store_name"
