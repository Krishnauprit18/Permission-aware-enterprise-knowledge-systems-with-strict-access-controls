# Development Workflow

## Commit convention

Use Conventional Commits: `<type>(PXX): <imperative summary>`. Allowed types include `feat`, `fix`, `security`, `docs`, `test`, `refactor`, `build`, and `chore`. Keep each commit focused on one coherent change. A security fix must include a regression test in the same phase whenever practical.

## Phase checkpoint

1. Finish only the requested phase scope.
2. Run all applicable checks and capture evidence.
3. Self-review the diff and resolve findings.
4. Update `CURRENT_STATE.md`, `TASK_LEDGER.md`, `TEST_STATUS.md`, `RISK_REGISTER.md`, and `PROMPT_LEDGER.md`.
5. Move the phase plan from `docs/exec-plans/active/` to `docs/exec-plans/completed/`.
6. Create a checkpoint commit only when requested or when the project workflow explicitly requires it, then record its hash in both ledgers.

If a required condition cannot be met, report `BLOCKED` with the exact reason. Do not convert an incomplete or failing phase into `PASS`.
