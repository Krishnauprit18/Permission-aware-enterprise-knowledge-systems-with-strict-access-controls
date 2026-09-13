# Quality Gates

These gates define a shift-left secure SDLC for local development. A later phase may make a gate more specific, but may not weaken a security invariant without an explicit ADR and user direction.

## Gate 0: scope and state

- Read `AGENTS.md`, `docs/state/CURRENT_STATE.md`, the active phase plan, and relevant design docs.
- Confirm the change is within the numbered phase and record assumptions.
- Update the durable state files before checkpointing.

## Gate 1: design and threat review

- Define typed interfaces and trust boundaries before implementation.
- Identify authorization, confidentiality, prompt-injection, data-retention, and failure-mode risks.
- Record material choices in an ADR; keep policy separate from model behavior.

## Gate 2: implementation hygiene

- Use strict linting and type checking; pin dependencies with lockfiles.
- Keep secrets out of code, fixtures, prompts, logs, and test output.
- Use migrations for schema changes and structured, redacted logs for operational events.
- Do not silently swallow exceptions; preserve actionable failure signals.

## Gate 3: security and behavior tests

- Add regression tests with every implementation change, especially for authorization.
- Prove protected paths deny by default and fail closed.
- Prove unauthorized evidence is excluded before retrieval output can reach an LLM, reranker, citation builder, or prompt.
- Test revocation/deletion/update behavior, citation validation, refusal paths, stale/conflicting evidence, and shareability separately from view permission as applicable.

## Gate 4: verification and review

- Run focused checks continuously and every applicable target from `make verify` before completion.
- Run security, dependency, secret, and static scans when the repository has the corresponding tooling.
- Self-review the diff for correctness, security, maintainability, unnecessary complexity, dead code, scope creep, and constitution violations.
- Record commands, versions where material, results, and residual risks in test or release evidence.

## P03 command matrix

Run `make bootstrap` once on a new checkout. It installs Python 3.12 through uv, syncs the locked backend environment, and runs `npm ci` against the frontend lockfile.

| Target | Runtime | Purpose |
| --- | --- | --- |
| `make fmt` | Fast | Check Ruff and Prettier formatting. |
| `make lint` | Fast | Run Ruff and ESLint. |
| `make lint-docs` | Fast | Run the lockfile-managed Markdown linter. |
| `make prompt-integrity` | Fast | Verify every archived phase prompt hash matches the prompt ledger. |
| `make typecheck` | Fast | Run strict mypy and TypeScript checks. |
| `make test-unit` | Fast | Run backend and frontend unit tests with coverage thresholds. |
| `make test-integration` | Fast | Run local package-boundary tests; no infrastructure is required in P03. |
| `make test-security` | Fast | Run Bandit, Semgrep, and security-marked regressions. |
| `make verify` | Fast | Run all deterministic P03 gates. |
| `make scan` | Slow | Run pip-audit, npm audit, detect-secrets, and Semgrep. |
| `make sbom` | Slow | Generate backend and frontend CycloneDX reports under ignored `reports/`. |
| `make shellcheck` | Slow | Analyze shell scripts when ShellCheck is installed. |
| `make container-lint` | Slow | Use Hadolint, or Docker's local `build --check` fallback. |
| `make container-scan` | Slow | Run Trivy configuration and high/critical severity checks for container definitions. |

## P04 platform checks

| Command | Runtime class | Required evidence |
|---|---|---|
| `make platform-config` | Fast | Generated mode-600 local env file and valid rendered Compose model. |
| `make up` | Slow | Health-gated startup, completed OpenFGA migration, and successful MinIO initializer. |
| `make platform-status` | Fast after startup | Compose service status plus PostgreSQL, OpenSearch, Keycloak, OpenFGA, MinIO, OTel, Jaeger, and Prometheus probes. |
| `make container-lint` | Fast/slow | Valid rendered Compose model plus Dockerfile lint or BuildKit checks. |
| `make reset-demo` | Slow and destructive | Empty named volumes recreated, platform readiness restored, and `raw` bucket initialized. |
| `make verify-release` | Slow | Run `verify` plus all release/security evidence targets. |

`make verify` is the required local development gate. `make verify-release` is required before a release or phase checkpoint when its external scanner prerequisites are available. Missing release tools must fail loudly and be recorded as a tooling gap; they must not be represented as a pass.

## Security-tooling policy

- Python and frontend dependencies are pinned by `backend/uv.lock` and `frontend/package-lock.json`.
- `make test-security` is deterministic and local; its Semgrep policy is the Python preset plus language-native checks.
- `make scan` performs dependency and secret checks. Findings are triaged by reachability, exploitability, and whether the dependency is in a shipped path.
- `make sbom` emits CycloneDX JSON for review and archival. Generated reports are ignored by Git and must not contain secrets.
- Container linting is syntax/policy validation. It validates the rendered Compose model and Dockerfiles. `make container-scan` requires local Trivy and checks the Compose and Dockerfile configuration at high and critical severity. Image vulnerability scanning is reserved for a later image-build phase; when an image exists, extend this target rather than treating lint as vulnerability coverage.

## Evidence standard

Record command, tool version, date, result, and relevant output summary in `docs/state/TEST_STATUS.md` or the release evidence template. A passing fast gate does not imply product functionality, live infrastructure readiness, or formal compliance certification.

## Blocking conditions

A phase or merge is blocked by any failing required check, unreviewed security finding, missing required test, leaked secret, unvalidated citation path, unauthorized context exposure, undocumented schema change, silent exception handling on a protected path, or unsupported compliance claim.
