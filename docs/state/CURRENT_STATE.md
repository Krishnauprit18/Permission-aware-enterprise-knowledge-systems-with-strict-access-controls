# Current State

## Snapshot

- Last updated: 2026-09-13
- Current phase: `P04`
- Phase status: `PASS`
- Repository baseline: empty Git repository on `master` with no prior commits at P00 inspection
- Product implementation: not started; P00-P02 establish documentation/contracts/architecture and P03 establishes only the typed repository scaffold and quality gates
- Checkpoint commits: P00 `fd13c0f`, P01 `5570e59`, P02 `f512236`, P03 `cc91683`; P04 is the current checkpoint.

## Established invariants

- Unauthorized chunks must be excluded before any LLM context, reranker input, embedding request, or citation construction.
- Authorization is deny-by-default, fail-closed, deterministic, and separate from LLM behavior.
- `can_view` and `can_share_externally` are distinct policy decisions.
- Evidence must be deterministic, grounded, citable, freshness/authority/conflict-aware, and traceable.
- Retrieved content is untrusted and may contain prompt injection.
- No secrets in repository or logs; schema changes require migrations; dependencies require pinning/lockfiles.

## P01 specification baseline

- Synthetic tenant scenario: Northstar Cloud Systems with Acme Retail, Beacon Health, Cedar Logistics, and an isolated Harbor Labs fixture.
- Normative product specification: `docs/00-product/PRODUCT_SPECIFICATION.md`.
- Required journeys: `docs/00-product/USER_JOURNEYS.md`.
- Normative invariant registry: `docs/00-product/SYSTEM_INVARIANTS.md`.
- Trust boundary model: `docs/01-architecture/TRUST_MODEL.md`.
- Threat register and planned tests: `docs/02-security/THREAT_MODEL.md`.
- Standards verification guidance: `docs/02-security/VERIFICATION_MATRIX.md`.
- Accepted P01 decisions: `docs/decisions/ADR-001-authorization-before-model-context.md`, `ADR-002-view-and-external-share-are-separate.md`, `ADR-003-untrusted-retrieved-content-and-deterministic-citations.md`, and `ADR-004-fail-closed-refusal-non-disclosure.md`.

## P02 architecture baseline

- Reference stack: strictly typed Python/FastAPI backend and local worker, React/TypeScript strict frontend, PostgreSQL control metadata, OpenSearch hybrid retrieval, OpenFGA relationship authorization, Keycloak OIDC, MinIO raw storage, local model adapters, OpenTelemetry, and Docker Compose.
- Redis is not in the initial architecture; introduction requires measured need and a new ADR.
- Component/data/deployment ownership: `docs/01-architecture/REFERENCE_ARCHITECTURE.md`.
- Mandatory ingestion, query, deletion/change, and role-change pipelines: `docs/01-architecture/PIPELINES.md`.
- Dynamic authorization and metadata-first candidate/fine-check design: `docs/01-architecture/AUTHORIZATION_ARCHITECTURE.md`.
- Typed ports, security-bearing types, layering, and import rules: `docs/01-architecture/PORTS_AND_DEPENDENCY_RULES.md`.
- API, index, embedding, prompt, evaluation, authorization, schema, component, and release versioning: `docs/01-architecture/VERSIONING.md`.
- P02 review evidence: `docs/01-architecture/ARCHITECTURE_REVIEW.md`.
- Accepted P02 decisions: ADR-005 through ADR-010 in `docs/decisions/`.

## P03 scaffold baseline

- Backend: Python `>=3.12,<3.13`, uv-managed `backend/uv.lock`, pyproject packaging, Ruff, strict mypy, pytest markers, and 90% coverage threshold.
- Frontend: React/TypeScript strict package, npm lockfile, ESLint, Prettier, Vitest, and 90% line/function/statement plus 85% branch coverage thresholds.
- Local gates: `make verify` is deterministic and PASS; `make verify-release` includes slower dependency, secret, SBOM, shell, and container checks.
- Security tooling: Bandit, Semgrep, detect-secrets baseline, pip-audit and npm audit for shipped runtime dependencies, CycloneDX SBOMs, and Docker BuildKit `build --check` fallback.
- Architecture protection: framework-independent domain/application contracts and an import-boundary test. Product workflows and infrastructure remain unimplemented.
- P03 evidence: `docs/03-engineering/QUALITY_GATES.md`, `TOOLCHAIN.md`, `FAILURE_TRIAGE.md`, and completed plan `docs/exec-plans/completed/P03.md`.

## Authoritative context

Read `AGENTS.md`, this file, the active phase plan, and only relevant documents before future work. See `docs/codex/PERSISTENCE_PROTOCOL.md` for the persistence contract.

## P04 local platform baseline

- `compose.yml` defines PostgreSQL, OpenSearch, Keycloak, OpenFGA, MinIO, OpenTelemetry Collector, Jaeger, and Prometheus on a private internal network. Redis remains intentionally absent.
- Host exposure is loopback-only. The verification daemon is `minikube-docker`, so smoke checks also support private-network probes without changing the default bindings.
- Healthchecks and dependency conditions gate startup. OpenFGA migrations run before OpenFGA; MinIO initialization is an explicit checked one-shot command.
- `scripts/bootstrap-platform.sh` generates ignored `.env.local` credentials with mode `0600`; no credential values are committed or printed. OpenSearch bootstrap passwords include its required character classes.
- Named volumes cover PostgreSQL, OpenSearch, Keycloak, MinIO, and Prometheus. `make down` preserves volumes. `make reset-demo` is implemented and dry-run verified but was not executed because it is destructive and no explicit deletion approval was provided.
- OTel exports traces to local Jaeger and metrics to Prometheus. `make platform-status` smoke checks all platform services plus health/version endpoints.
- `docs/05-operations/LOCAL_PLATFORM.md` records ports, local-only posture, credentials, backup/reset semantics, data locations, container users, and failure triage.
- P04 evidence: `make platform-config`, `make up`, `make platform-status`, `make container-lint`, `make shellcheck`, `make container-scan`, `make verify`, `make scan`, `make sbom`, and `make verify-release` passed. No product business features were added.

## Next authorized work

No future phase is authorized by this record. Await an explicit P05 prompt.
