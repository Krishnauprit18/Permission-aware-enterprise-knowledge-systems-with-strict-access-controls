# Engineering Constitution

This repository builds a local-only, permission-aware enterprise knowledge system. This file is the compact constitution and table of contents; durable detail belongs in the linked documents.

## Non-negotiable invariants

- Authorization is enforced before retrieved results can enter reranking, evidence resolution, citation construction, an LLM context, export, or answer caches. Post-generation filtering is never authorization. Ingestion-time local embeddings are derived-data work after trusted ACL/classification validation, not a user authorization grant.
- Deny by default and fail closed on protected authorization paths. `can_view` and `can_share_externally` are separate decisions.
- LLMs never make authorization or security-classification decisions. Retrieved content is untrusted input and may contain prompt injection.
- Every answer is grounded in deterministic, validated, citable evidence; traces are auditable and logs are structured and redacted.
- No secrets belong in source, fixtures, prompts, documentation, or logs. Schema changes require migrations, and dependencies require pinned lockfiles.
- Typed interfaces, strict linting/type checking, tests with implementation, focused checks, and required phase gates are mandatory.
- No silent exception swallowing, weakened security controls, unsupported compliance claims, or phase-scope expansion.

## Required reading order

1. `AGENTS.md` and `docs/state/CURRENT_STATE.md`
2. The active phase plan under `docs/exec-plans/active/`
3. Only the relevant design, security, engineering, evaluation, or operations documents
4. `docs/decisions/` ADRs when a recorded decision is relevant

## Project map

- Product scope and invariants: `docs/00-product/`
- Architecture and interfaces: `docs/01-architecture/`
- Security policy, threat model, and findings: `docs/02-security/`
- Workflow, quality gates, and evidence: `docs/03-engineering/`
- Retrieval/generation evaluation and golden data: `docs/04-evals/`
- Local runtime and operations: `docs/05-operations/`
- Architecture decisions: `docs/decisions/`
- Executable phase plans: `docs/exec-plans/active/` and `docs/exec-plans/completed/`
- Durable state, ledgers, and test status: `docs/state/`
- Sanitized phase prompts and persistence rules: `docs/codex/`
- Placeholder task runner: `Makefile`

## Change and checkpoint convention

Use Conventional Commits with a phase scope, for example `feat(P01): add authorization model` or `docs(P00): bootstrap engineering constitution`. Keep commits small and reviewable. A phase checkpoint is allowed only after the phase exit gate passes, required evidence is recorded in `docs/state/`, the active plan is moved to `docs/exec-plans/completed/`, and the checkpoint commit hash is recorded in `TASK_LEDGER.md` and `PROMPT_LEDGER.md`. Never mark a phase complete to hide failing checks.
