# Current State

## Snapshot

- Last updated: 2026-09-13
- Current phase: `P06`
- Phase status: `PASS`
- Repository baseline: empty Git repository on `master` with no prior commits at P00 inspection
- Product implementation: P05 provides local identity/authentication and P06 provides the first-class OpenFGA authorization boundary; ingestion, retrieval, indexing, reranking, generation, and product persistence remain unimplemented.
- Checkpoint commits: P00 `fd13c0f`, P01 `5570e59`, P02 `f512236`, P03 `cc91683`, P04 `35801fc`, P05 `03be6c1`; P06 implementation checkpoint pending.

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

## P05 identity and authentication baseline

- Local Keycloak realm bootstrap is deterministic and synthetic: a public browser client uses Authorization Code + S256 PKCE; demo passwords are generated into ignored mode-600 `.env.local` and are never committed or logged.
- Backend OIDC validation is fail-closed and typed. It validates the configured issuer, audience, RS256 algorithm, JWKS signature, required claims, expiry, not-before, issued-at, and an explicit bounded clock-skew policy before producing a principal.
- The browser keeps access tokens in memory only. Only transient PKCE state/verifier values use session storage; no access or ID token is written to localStorage or sessionStorage.
- Auth endpoints expose generic errors, emit allowlisted structured diagnostics, attach correlation IDs, and provide local-process session revocation plus browser logout. Resource authorization remains a later server-side OpenFGA/application decision.
- P05 evidence: focused auth tests, full `make verify`, full `make verify-release`, Keycloak bootstrap, OIDC discovery, and `make platform-status` passed. TestClient emitted non-failing upstream deprecation warnings.
- P05 residual risks: in-process revocation is not a multi-process session store, and already-issued tokens can outlive a Keycloak user disable until provider status/back-channel enforcement exists. Both are documented in `docs/02-security/AUTHENTICATION_MODEL.md` and the risk register.
- P05 checkpoint commit: `03be6c1` (`feat(P05): implement identity and authentication`) is pushed to `origin/master`.

## P06 authorization baseline

- OpenFGA schema 1.1 model v1 covers tenant, tenant-scoped groups, departments, accounts, projects, resources, direct viewer/owner, restricted viewer, and separate share reviewer relationships.
- `OpenFGAAdapter` is the backend policy enforcement point. It checks server-owned resource metadata and tenant membership before current high-consistency OpenFGA relationship checks; client filters, identity group claims, search metadata, and LLM behavior cannot grant access.
- `can_view` and `can_share_externally` remain separate. Trusted classification metadata gates external sharing, and trusted restricted metadata selects the explicit `restricted_viewer` path instead of inherited access.
- Permission-first listing returns metadata-only IDs and a versioned scope. Unknown/cross-tenant objects are discarded; authorizer transport, timeout, status, and malformed-response failures return deny/indeterminate or raise `AuthorizationUnavailable`.
- Decisions carry `authorization_model_id`, `tuple_version`, `policy_version`, reason code, correlation ID, duration audit fields, and a SHA-256 fingerprint for future cache binding. The fingerprint contains no relationship graph details.
- Deterministic local model and tuple state is bootstrapped by `make openfga-bootstrap` and wired into `make up`/`reset-demo`; OpenFGA state is stored in the local PostgreSQL database.
- P06 permission matrix fixture: `docs/04-evals/permission_matrix.json`.
- P06 evidence: `make verify`, `make verify-release`, `make shellcheck`, integrated `make up`, `make platform-status`, two idempotent `make openfga-bootstrap` runs, and live relationship probes passed. P06 implementation checkpoint commit is pending.

## Next authorized work

No future phase is authorized by this record. Await an explicit P07 prompt.
