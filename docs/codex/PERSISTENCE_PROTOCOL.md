# Persistence Protocol

Durable project state lives in the repository. Historical chat and model memory are not required to continue work.

## Required phase records

1. Store the exact phase prompt once under `docs/codex/prompts/PXX.md` after removing or replacing secrets with `[REDACTED_SECRET]`.
2. Store a short summary, SHA-256 hash, outcome, and checkpoint commit in `docs/state/PROMPT_LEDGER.md`.
3. Record the phase outcome, scope, and checkpoint in `docs/state/TASK_LEDGER.md`.
4. Update `docs/state/CURRENT_STATE.md`, `TEST_STATUS.md`, and `RISK_REGISTER.md` at the phase checkpoint.
5. Promote decisions that matter into ADRs or durable design documents.

## Future reading contract

At the start of each phase, read `AGENTS.md`, `docs/state/CURRENT_STATE.md`, the active phase plan, and only the relevant design documents. Do not reread all historical prompts. Use the prompt archive for audit or exact wording only.

## Sanitization and integrity

Prompt archives and evidence must not contain credentials, tokens, private keys, password material, or unnecessary personal data. Use `[REDACTED_SECRET]` for a secret reference that must remain understandable. Hash the sanitized file bytes with SHA-256 after writing it. A changed prompt requires a new phase record, not an overwritten historical record.

## Checkpoint rule

A phase is complete only when its applicable checks pass, its state records are updated, its sanitized prompt is archived, risks are recorded, and the gate is explicitly `PASS`. A blocked phase remains `BLOCKED` until the blocking condition is resolved; never infer completion from elapsed time or partial implementation.
