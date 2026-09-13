# Local Toolchain

## Runtime choices

- Python `>=3.12,<3.13`, managed by uv for ecosystem compatibility and reproducible environments.
- Node and npm are used for the small React/TypeScript frontend. The repository records the resolved dependency graph in `frontend/package-lock.json`.
- Ruff provides Python formatting and linting. Its rules include import hygiene, common bug patterns, security checks, timezone checks, and modern Python upgrades.
- mypy runs in strict mode over `backend/src` and `backend/tests`.
- ESLint, Prettier, TypeScript, Vitest, and V8 coverage provide frontend checks. Playwright is intentionally reserved for a later E2E phase.

## Reproducible setup

```bash
make bootstrap
```

This command downloads only declared local development dependencies, creates the uv-managed Python environment, and installs the exact npm lockfile graph. Do not commit `.venv/`, `node_modules/`, coverage output, or generated reports.

## Local hooks

```bash
uv run --directory backend pre-commit install
uv run --directory backend pre-commit run --all-files
```

Pre-commit runs whitespace and key checks plus the repository's Ruff, mypy, Prettier, and ESLint hooks. Hooks are advisory during early P03 bootstrap until the environment has been installed; the Makefile gates remain authoritative.

## Security and supply-chain commands

```bash
make test-security
make scan
make sbom
make container-lint
make container-scan
```

`make scan` requires `pip-audit` and `detect-secrets` from the backend development group, the locally installed Semgrep executable, and npm registry metadata for `npm audit`. `make container-lint` validates the rendered Compose model, then prefers Hadolint and otherwise uses Docker BuildKit's `docker build --check` when supported. `make container-scan` requires Trivy and checks Compose plus Dockerfile configuration. ShellCheck, Hadolint, Trivy, Syft, and Gitleaks are explicit local prerequisites when their deeper release checks are enabled; no hosted CI is required.

## P04 platform commands

| Command | Runtime class | Behavior |
|---|---|---|
| `make platform-config` | Fast | Generates ignored `.env.local` credentials and validates Compose interpolation. |
| `make up` | Slow | Starts only after health-gated dependencies are ready, runs platform migrations, and initializes the private MinIO bucket. |
| `make platform-status` | Fast after startup | Runs service status and endpoint smoke checks. It supports VM-backed Docker contexts with private-network probes. |
| `make down` | Fast | Removes project containers and network while preserving named volumes. |
| `make reset-demo` | Slow/destructive | Removes project containers, network, and named volumes, then recreates the empty platform. |

The Compose file contains no passwords. Secret values come from `.env.local`, which is generated with mode `0600` and excluded by `.gitignore`. Pinned tags and verified digests are reviewed as infrastructure dependencies; Trivy remains the release gate for image/config vulnerability scanning when available.
