#!/usr/bin/env bash
set -euo pipefail

ledger="${1:-docs/state/PROMPT_LEDGER.md}"
prompt_dir="${2:-docs/codex/prompts}"

[[ -f "$ledger" ]] || { printf 'Missing prompt ledger: %s\n' "$ledger" >&2; exit 1; }
[[ -d "$prompt_dir" ]] || { printf 'Missing prompt directory: %s\n' "$prompt_dir" >&2; exit 1; }

checked=0
while IFS= read -r line; do
  if [[ "$line" =~ \|[[:space:]](P[0-9]{2}R?)[[:space:]]\|.*\`([0-9a-f]{64})\` ]]; then
    phase="${BASH_REMATCH[1]}"
    expected="${BASH_REMATCH[2]}"
    prompt="$prompt_dir/${phase}.md"
    [[ -f "$prompt" ]] || { printf 'Missing prompt archive: %s\n' "$prompt" >&2; exit 1; }
    actual="$(sha256sum "$prompt" | awk '{print $1}')"
    [[ "$actual" == "$expected" ]] || {
      printf 'Prompt hash mismatch for %s: ledger=%s actual=%s\n' "$phase" "$expected" "$actual" >&2
      exit 1
    }
    checked=$((checked + 1))
  fi
done < "$ledger"

(( checked > 0 )) || { printf 'No prompt rows were checked\n' >&2; exit 1; }
printf 'Prompt integrity passed: %d archived prompts verified.\n' "$checked"
