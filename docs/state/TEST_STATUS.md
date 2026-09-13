# Test Status

## P00

- Scope: documentation, repository policy, templates, and placeholder Make targets.
- Implementation tests: none applicable; no product code exists.
- Required checks run:
  - `make verify`
  - `make bootstrap`
  - `make sbom`
  - `make scan`
  - structural and content assertions for required paths and policy phrases
- Result: `PASS` for P00 placeholder/documentation scope.
- Known gaps: real formatters, linters, type checker, test runners, SBOM generator, and scanners will be selected when implementation begins.

## P01

- Scope: product specification, journeys, invariants, trust model, threat model, standards verification matrix, ADRs, prompt archive, and state updates.
- Implementation tests: none applicable; P01 explicitly forbids feature implementation.
- Required checks run:
  - `make verify bootstrap sbom scan`
  - `npx --yes markdownlint-cli2 'AGENTS.md' 'docs/**/*.md'`
  - structural Markdown assertions for required product terms, ten journeys, seven required invariant IDs, 21 threat IDs, and five standards references
  - required path and content review
  - trailing-whitespace audit
  - prompt archive SHA-256 integrity audit
  - product implementation file audit
- Result: `PASS` for P01 specification-only scope.
- Markdown lint result: `markdownlint-cli2 v0.23.2` with `markdownlint v0.41.1`, 39 authored Markdown files, 0 issues. Exact prompt archives are excluded by `.markdownlint-cli2.yaml` and remain protected by SHA-256 ledger checks.

## P02

- Scope: reference architecture, four mandatory pipelines, dynamic authorization, typed ports and import rules, versioning, architecture review, six technology ADRs, prompt archive, and state updates.
- Business implementation tests: none applicable; P02 contains no product code or deployment artifacts.
- Required checks run:
  - `npx --yes markdownlint-cli2 'AGENTS.md' 'docs/**/*.md'`
  - architecture assertions for the selected stack, server-generated filters, metadata-only candidates, fine checks, authorization-bearing types, and no re-embedding on relationship change
  - required port assertions for connector, parser, chunker, embedder, search, authorization, reranker, LLM, evidence resolver, and audit sink
  - mandatory pipeline-order and API/index/embedding/prompt/evaluation-version assertions
  - ADR structure/status review for ADR-005 through ADR-010
  - scope audit confirming no business implementation files
  - P02 prompt SHA-256 and ledger integrity checks
- Result: `PASS` for P02 architecture-only scope.
- Markdown lint result: `markdownlint-cli2 v0.23.2` with `markdownlint v0.41.1`, 52 authored Markdown files, 0 issues on the final P02 tree.

## P03

- Scope: typed backend/frontend scaffold, reproducible dependencies, developer controls, local fast/release gates, boundary tests, and engineering documentation. No product features implemented.
- Environment: uv `0.12.13` with managed CPython `3.12.14`; Node `v24.5.0`; npm `11.13.0`; Docker `29.7.2`; Semgrep locally installed; ShellCheck and Trivy unavailable on this host.
- Required fast gate: `make verify` PASS.
- Fast evidence: Ruff format/check, Prettier, ESLint, Markdown lint (`markdownlint-cli2 v0.18.1`, 53 files, 0 errors), strict mypy, strict TypeScript, 2 backend unit tests at 100% measured domain coverage, 2 frontend unit tests at 100% configured source coverage, 1 architecture integration test, Bandit PASS, Semgrep PASS with 0 findings, and 2 security-marked regression tests.
- Release evidence: `make scan` PASS for shipped runtime dependencies, npm runtime dependencies, secrets, and Semgrep. `make sbom` PASS with backend/frontend CycloneDX output. `make container-lint` PASS using Docker BuildKit `build --check` for both Dockerfiles.
- Release gate: `make verify-release` BLOCKED before completion because ShellCheck and Trivy are not installed. An attempted apt installation could not acquire the system package lock without root access. This is an explicit tooling gap, not a waived check.
- Repository controls: `uv run --project backend pre-commit run --files ...` PASS for representative backend, frontend, documentation, manifest, and shell files. The `--all-files` form was skipped by pre-commit because this baseline repository has no tracked files yet.
- Known advisory scope: a prior full development-graph audit reported `lxml 5.4.0` and was not promoted to shipped runtime dependencies because the SBOM tool constrains lxml below 6; runtime audit is clean. Revisit before treating the development environment as release-hardened.

## P04

- Scope: local Docker Compose infrastructure only. No product schemas, connectors, retrieval, models, authorization tuples, or demo data were implemented.
- Platform: PostgreSQL, OpenSearch 2.17.1, Keycloak 26.0.6, OpenFGA 1.8.3, MinIO, OTel Collector 0.110.0, Jaeger 1.62.0, and Prometheus 2.54.1 on a private internal network with loopback-only host bindings.
- Configuration: `make platform-config` PASS; generated `.env.local` is mode `0600`; Compose interpolation PASS; no committed secret values.
- Startup: `make up` PASS with health-gated dependencies, successful OpenFGA migration, and successful MinIO bucket initialization.
- Smoke: `make platform-status` PASS for PostgreSQL readiness, OpenSearch health/version, Keycloak readiness/master realm, OpenFGA health, MinIO liveness, OTel health, Jaeger UI, and Prometheus readiness. The private-network fallback was used for the active `minikube-docker` context.
- Static/container: `make container-lint` PASS with Compose validation and Docker BuildKit checks; `make shellcheck` PASS using a pinned local fallback; `make container-scan` PASS using pinned Trivy `0.56.2` with embedded checks.
- Full gate: `make verify`, `make scan`, `make sbom`, and `make verify-release` PASS. `make -n reset-demo` confirms destructive volume reset plus deterministic re-bootstrap; live reset was not run because it deletes named volumes and no explicit deletion approval was provided.
- Known gap: MinIO runs as root in the pinned image configuration due entrypoint/named-volume behavior; this is documented for future hardening.

## P05

- Scope: local Keycloak/OIDC identity and authentication only. No retrieval, indexing, authorization tuple, or answer-generation workflow was implemented.
- Focused backend evidence: `uv run --directory backend pytest tests/unit/test_authentication.py -q --no-cov` passed 10 tests; `uv run --directory backend pytest tests/integration/test_auth_api.py -q --no-cov` passed 3 tests.
- Frontend evidence: `npm test -- --run` passed 13 tests with Vitest source coverage at 98.87% overall and 100% branch/function/line coverage for the configured application source. Access-token storage remains memory-only in tested flows.
- Fast gate: `make verify` passed, including Ruff format/check, strict mypy, strict TypeScript, ESLint, Prettier, Markdown lint, unit/integration/security tests, Bandit, Semgrep, and coverage thresholds.
- Release gate: `make verify-release` passed, including dependency audit, npm audit, detect-secrets, SBOM generation, pinned ShellCheck fallback, container lint, and Trivy configuration scans.
- Live evidence: `make up`, Keycloak demo bootstrap, private-network OIDC discovery validation, and `make platform-status` passed. No generated credentials were printed or tracked.
- Known non-failing warnings: Starlette TestClient and AnyIO emitted upstream deprecation warnings; they do not fail the gate and should be revisited when the test client dependency is refreshed.

## P06

- Scope: first-class OpenFGA authorization only. No retrieval, indexing, chunk text, model, or answer-generation workflow was implemented.
- Focused evidence: `uv run --directory backend pytest tests/unit/test_authorization.py -q --no-cov` passed 13 tests. Coverage includes account inheritance, cross-account denial, group/department grant, explicit restricted access, direct grants, revocation on the next request, unknown resources, authorizer outage, tenant isolation, resource tenant binding, metadata-only listing, audit fingerprints, and separate external sharing.
- Live evidence: `make openfga-bootstrap` passed twice, including the idempotent path. Read-only OpenFGA checks passed for account inheritance, cross-account denial, restricted/legal access, group/department inheritance, and tenant isolation.
- Full fast gate: `make verify` passed with 25 unit-selected tests, 4 integration tests, 28 security-selected tests, strict mypy/TypeScript, Ruff, ESLint, Prettier, Markdown lint, Bandit, and Semgrep. Backend domain coverage was 91.94%, above the 90% threshold; frontend configured source coverage was 98.87%.
- Full release gate: `make verify-release` passed with dependency audit, npm audit, detect-secrets, SBOM generation, pinned ShellCheck fallback, Dockerfile/Compose lint, and Trivy configuration scans. No known shipped dependency vulnerabilities were reported.
- Platform evidence: integrated `make up` passed health-gated startup, MinIO initialization, Keycloak bootstrap, and OpenFGA model/tuple bootstrap; `make platform-status` passed all service probes. `make openfga-bootstrap` passed twice, including the idempotent path. Live checks passed for account inheritance, cross-account denial, restricted/legal access, group/department inheritance, and tenant isolation.
- Known non-failing warnings: Starlette TestClient and AnyIO emitted upstream deprecation warnings in existing API tests; revisit when the test-client dependency is refreshed.
- Post-final check: after the fail-closed list wrapper was formatted, the focused authorization suite, Ruff, and mypy passed again. A separate full `make verify` rerun reached the existing auth integration test and was stopped by a 45-second timeout without an assertion result; the completed full fast and release gates above passed before this formatting-only/post-check adjustment.

## P07

- Scope: canonical PostgreSQL control metadata only. No connectors, OpenSearch retrieval, chunk text, model, or answer-generation workflow was implemented.
- Focused unit evidence: `make test-unit` passed 31 backend-selected tests with 97.98% backend domain coverage and 13 frontend tests with 98.87% configured frontend coverage.
- Focused integration evidence: `P07_DATABASE_HOST=172.18.0.4 uv run --directory backend pytest tests/integration/test_persistence_postgres.py -q --no-cov` passed 5 tests against an isolated PostgreSQL schema, covering empty migration, idempotent seed/lineage reconstruction, transaction rollback, version identity conflict, tenant-safe integrity rejection, and deletion/tombstone markers.
- Migration evidence: `make db-migrate` applied `0001_initial` and a repeat invocation reported `Already applied: 0001_initial`; `make db-schema-doc` generated `docs/generated/db-schema.md` from the live database.
- Fast/release evidence: final `make verify-release` passed with Ruff, Prettier, ESLint, Markdown lint (`markdownlint-cli2 v0.18.1`, 67 files, 0 errors), strict mypy/TypeScript, unit/integration/security tests, Bandit, Semgrep, dependency audit, npm audit, detect-secrets, CycloneDX SBOM, ShellCheck fallback, Docker BuildKit checks, and Trivy configuration checks.
- Non-failing warnings: Starlette TestClient and AnyIO emitted existing upstream deprecation warnings. Default aggregate integration runs skip the P07 PostgreSQL tests when the private Docker context is not exposed to localhost; the focused host-addressed run above is the authoritative P07 database evidence.

## P08

- Scope: deterministic synthetic enterprise demo/evaluation corpus, ACL fixtures, golden cases, content validator, and documentation. No runtime ingestion, retrieval, indexing, model, or answer-generation workflow was implemented.
- Dataset evidence: 15 source items across document, support-ticket, Slack-thread, call-transcript, policy, and hourly-feed types; 4 accounts across 2 tenants; 6 synthetic users; 15 ACL resources; and 60 golden cases. Required scenario labels and evidence authority/freshness relationships validate successfully.
- Focused evidence: `make dataset-validate` passed; `uv run --directory backend pytest -m 'unit and security' tests/unit/test_synthetic_dataset.py --no-cov` passed 3 tests; strict mypy, Ruff, and formatting checks passed for the validator/tests.
- Fast gate: `make verify` passed. Backend unit tests passed 34 selected tests with 97.98% domain coverage; frontend tests passed 13 tests with 98.87% configured coverage; the default integration run passed 4 tests and skipped 5 PostgreSQL tests because the local database was not exposed; security tests passed 32 tests with 2 PostgreSQL skips; Bandit and Semgrep passed with 0 findings.
- Release gate: `make verify-release` passed, including Markdown lint (`markdownlint-cli2 v0.18.1`, 69 files, 0 errors), dependency audits with no known vulnerabilities, detect-secrets, CycloneDX SBOM generation, ShellCheck fallback, Docker BuildKit checks, and Trivy configuration scans.
- Known non-failing warnings: existing Starlette TestClient and AnyIO deprecation warnings remain. No P08-specific warning or failure was introduced.

## P09

- Scope: synthetic document/filesystem, support-ticket, Slack-thread, and call
  transcript connectors plus raw-ingestion orchestration. No parsing, chunking,
  embedding, OpenSearch indexing, retrieval, reranking, or generation.
- Focused evidence: `uv run --directory backend pytest tests/unit/test_ingestion.py -q` passed 14 tests covering first sync, unchanged replay, update, deletion, malformed and missing records, interruption/restart, duplicate identity, hostile path, ACL mapping, bounded retry, log hygiene, and object-store integrity.
- Fast gate: `make verify` passed. Backend unit tests passed 48 selected tests
  with 93.29% measured domain coverage; frontend tests passed 13 tests with
  98.87% configured coverage; integration passed 4 tests with 5 PostgreSQL
  skips in the default private-platform environment; security passed 39 tests
  with 2 PostgreSQL skips; Ruff, strict mypy, TypeScript, Markdown lint,
  Bandit, and Semgrep passed.
- Release gate: `make verify-release` passed. Runtime dependency audits found
  no known vulnerabilities, npm audit passed, detect-secrets passed, SBOMs
  generated, and ShellCheck/container lint/Trivy configuration checks passed
  through the pinned local fallback containers.
- Non-failing warnings: existing Starlette TestClient and AnyIO deprecation
  warnings remain. The release scan rewrites `.secrets.baseline` generation
  time; it was restored to the tracked value before checkpointing.

## P10

- Focused content evidence: `uv run --directory backend pytest tests/unit/test_content_pipeline.py -q --no-cov` passed 11 tests. Coverage includes document/policy-style sections, tables/code blocks, nested Slack replies, ticket comment windows, transcript turn locators, malformed Unicode, active-content stripping, prompt-injection-as-data, empty/huge inputs, bounds, restricted metadata/ACL propagation, versioned IDs, unknown classification, malformed JSON, and unsupported/deep sources.
- Fast gate: `make verify` passed. Backend unit tests passed 59 selected tests with 90.30% measured domain coverage; frontend tests passed 13 tests with 98.87% configured coverage; integration passed 4 tests with 5 PostgreSQL skips in the default private-platform environment; security passed 40 tests with 2 PostgreSQL skips; Ruff, strict mypy, TypeScript, Markdown lint, Bandit, and Semgrep passed.
- Release gate: `make verify-release` passed. Runtime dependency audits found no known vulnerabilities, npm audit passed, detect-secrets passed, SBOMs generated, and ShellCheck/container lint/Trivy configuration checks passed through the pinned local fallback containers.
- Markdown tooling note: the baseline environment did have the repository's pinned `markdownlint-cli2` available during P10 verification; when the uv cache was read-only, the gate was rerun with approved local cache access. The existing tooling-gap record remains applicable to environments where `markdownlint` is unavailable and structural checks are the fallback.
- Non-failing warnings: existing Starlette TestClient and AnyIO deprecation warnings remain. The release scan rewrites `.secrets.baseline` generation time; it was restored to the tracked value before checkpointing.
