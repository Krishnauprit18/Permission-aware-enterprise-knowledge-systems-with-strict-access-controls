# Current State

## Snapshot

- Last updated: 2026-09-14
- Current phase: `P13`
- Phase status: `PASS`
- Repository baseline: empty Git repository on `master` with no prior commits at P00 inspection
- Product implementation: P05 provides local identity/authentication, P06 provides the first-class OpenFGA authorization boundary, P07 provides canonical PostgreSQL metadata persistence, P08 provides deterministic synthetic demo/evaluation fixtures plus validation, P09 provides typed fixture connectors plus raw-ingestion orchestration, P10 provides source-aware parsing/chunking, P11 provides local embedding and disposable OpenSearch indexing, P12 provides permission-first hybrid retrieval, and P13 provides bounded local reranking plus deterministic evidence resolution; context construction, citation validation, external sharing, and generation remain unimplemented.
- Checkpoint commits: P00 `fd13c0f`, P01 `5570e59`, P02 `f512236`, P03 `cc91683`, P04 `35801fc`, P05 `03be6c1`, P06 `acb3083`, P07 `801a788`, P08 implementation `3a1b01f`, P09 implementation `7fabcf0`, P10 implementation `e112207`, P11 implementation `ebb66b9`, P11 remediation `09df9a4`, P12 implementation `a927cb9`, P12 verification `fb10e3d`, P12 docs checkpoint `51d68bf`, P13 implementation `9fca6df`, P13 docs checkpoint `c7f5a4a`.

## Established invariants

- Unauthorized chunks must be excluded before any user-query reranker input, evidence resolution, LLM context, citation construction, export, or answer cache. Ingestion embeddings are local sensitive derivatives created only after trusted ACL/classification validation and never grant access.
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
- P06 evidence: `make verify`, `make verify-release`, `make shellcheck`, integrated `make up`, `make platform-status`, two idempotent `make openfga-bootstrap` runs, and live relationship probes passed. P06 implementation checkpoint `acb3083` is pushed to `origin/master`.

## P07 canonical persistence baseline

- PostgreSQL migration `backend/migrations/0001_initial.sql` defines tenants, principal references, accounts, source connections/items, document versions, chunk metadata, ingestion jobs/checkpoints, deletion tombstones, query trace metadata, and evaluation datasets/cases/runs. Raw content, credentials, and authorization truth remain outside these tables.
- Domain objects are typed, UTC-aware, framework-independent, and enforce stable chunk identity, lifecycle/deletion consistency, shareability classification, lineage, retention, and non-empty identity/reference fields.
- `PostgresUnitOfWork` owns explicit commit/rollback/close behavior. The adapter uses parameterized SQL and never creates or alters schema at runtime; tenant/source identity conflicts fail closed instead of rebinding existing rows.
- `scripts/migrate-database.sh` applies ordered migrations with SHA-256 checksum drift detection and transactional ledger updates. `scripts/generate-db-schema-doc.sh` generated `docs/generated/db-schema.md` from the live database.
- P07 evidence: full `make verify-release` passed; focused PostgreSQL migration/repository tests passed 5 tests against the running private platform database; migration apply and repeat-idempotency checks passed; backend domain coverage is 97.98% and frontend configured coverage is 98.87%.
- P07 implementation checkpoint: `801a788` (`feat(P07): implement canonical persistence`) is pushed to `origin/master`; this state checkpoint records the final implementation hash.

## P08 synthetic dataset baseline

- `data/synthetic/` contains the versioned `northstar-enterprise-demo-eval` corpus: 15 source items, 4 accounts across 2 tenants, 6 synthetic principals, six source types, OpenFGA-shaped ACL mappings, and 60 golden retrieval/refusal cases.
- Deliberate evidence covers stale and superseded versions, current authoritative and customer-safe corroboration, informal conflict, Legal-only content, deletion, hourly updates, indirect prompt injection, and a separate Harbor Labs cross-tenant decoy.
- `knowledge_system.dataset.validator` validates deterministic IDs, source hashes and paths, tenant/ACL/lifecycle/lineage consistency, authority/freshness profiles, required labels/types, and secret-like or email-shaped content. It does not generate or store model answers.
- `make dataset-validate` is a fast deterministic fixture check and is part of `make verify`. `make seed-demo` validates the fixtures only; automatic platform ingestion/database loading remains future work.
- P08 evidence: `make verify` and `make verify-release` passed. The default aggregate integration runs continue to skip five PostgreSQL tests when the local database is not exposed; this is an existing environment condition and not a P08 fixture failure.
- P08 implementation checkpoint: `3a1b01f` (`feat(P08): add synthetic enterprise dataset`) is pushed to `origin/master`.
- P08 state checkpoint is anchored to implementation commit `3a1b01f`; the follow-up documentation commit contains the completed plan, prompt archive, and final ledgers.

## P09 connector and ingestion baseline

- `knowledge_system.application.ports.ingestion` defines typed connector,
  raw-store, relationship-intent, and ingestion-persistence ports. The
  application layer does not import MinIO, PostgreSQL, OpenFGA, or framework
  implementations.
- Fixture adapters cover document, support-ticket, Slack-thread, and optional
  call-transcript source types. They enforce root containment, type/size
  limits, UTC metadata, duplicate identity rejection, ACL mapping, malformed
  input isolation, and byte-to-manifest hash verification.
- `IngestionOrchestrator` is idempotent by stable job/checkpoint/tombstone and
  version identities. It stores active raw bytes before future parsing,
  persists metadata/version, hands ACL intents to a dedicated sink, removes
  deleted relationships, records tombstones, and checkpoints only afterward.
- Raw object references are verified for content hash and size. MinIO receives
  tenant/source/version/hash keys and allowlisted provenance metadata. No
  connector fetches arbitrary URLs or attachment references.
- Item failures are isolated and logged with stable IDs/reason codes only.
  Interrupted work is replayable and a returned cursor does not cross a
  failure gap. P09 does not parse, chunk, embed, index, retrieve, rerank, or
  generate answers.
- P09 evidence: `make verify`, `make verify-release`, and 14 focused ingestion
  tests passed. Default aggregate integration continues to skip five
  PostgreSQL tests when the private database is not exposed to localhost.
- P09 implementation checkpoint: `7fabcf0` (`feat(P09): implement connector ingestion orchestration`) is pushed to `origin/master`.

## P10 parsing and chunking baseline

- `knowledge_system.domain.content` defines typed source locators, parsed and
  normalized documents, bounded content chunks, deterministic lexical token
  counts, chunking limits, metrics, and conservative classification resolution.
- `FixtureContentParser` handles document/policy/contract sections, nested
  Slack threads, support-ticket metadata/comments, transcript turn windows,
  and structured hourly records. `SafeContentNormalizer` applies UTF-8
  replacement, Unicode NFC, line/control normalization, and active-content
  removal without executing source text.
- `BoundedContentChunker` respects semantic blocks first, then line/word
  boundaries, with a character split only for an unbreakable token. Every
  emitted chunk retains parent document/version, tenant/account/department,
  timestamps, classification/shareability, authority, ACL references, hashes,
  and source-native citation locators. No embedding or index write exists.
- P10 focused evidence: 11 content-pipeline tests passed; the full unit gate
  passed 59 tests with 90.30% domain coverage; the default integration gate
  passed 4 tests and skipped 5 PostgreSQL tests because the private database
  was not exposed; security passed 40 tests with 2 PostgreSQL skips.
- P10 `make verify` and `make verify-release` passed, including Markdown lint
  (73 files, 0 errors), strict mypy/Ruff/TypeScript, Bandit, Semgrep, runtime
  dependency audit, npm audit, detect-secrets, SBOM, ShellCheck fallback,
  Docker BuildKit checks, and Trivy configuration scans.
- P10 implementation checkpoint: `e112207` (`feat(P10): implement parsing and chunking pipeline`) is pushed to `origin/master`.
- P10 known limits: parser support is limited to the bounded source shapes in
  the synthetic corpus; the lexical token count is a safety bound rather than
  a model tokenizer; persistence, embedding, indexing, retrieval, and live
  authorization integration remain later phases.

## P11 embeddings and search index baseline

- `knowledge_system.domain.embedding` defines a typed provider boundary, explicit model name/version/dimension configuration, a local FastEmbed ONNX semantic adapter, a deterministic hash test double, bounded batches, timeout handling, bounded retries, and fail-closed provider/version validation. Runtime reindexing requires a local model artifact and has no cloud transport.
- `knowledge_system.domain.indexing` defines the versioned `v1` OpenSearch schema and deterministic searchable derivative documents. The mapping is strict and contains BM25 text, `knn_vector`, tenant/account/department/classification/authority/freshness, parent/version, provenance, citation locators, and ACL relationship references.
- `IndexingService` creates immutable generation names, embeds only bounded chunk batches, bulk indexes derived documents, and performs controlled alias cutover. The OpenSearch adapter is a private/local HTTP adapter with redacted errors, no payload logging, and explicit chunk/document deletion operations.
- `make reindex-demo` is the local operator path. It reads synthetic fixture envelopes through P10 parsing, requires a local FastEmbed ONNX model cache, and writes only through the internal adapter; it does not expose search to the browser and does not resolve authorization or implement user retrieval.
- P11 remediation evidence: FastEmbed BGE-small was installed into an ignored local cache and exercised with `local_files_only=True`; the live OpenSearch integration suite passed 2 tests covering generation creation, `index.knn=true`, bulk fixture indexing, mapping inspection, semantic ANN, BM25, alias cutover, deletion visibility, and generation cleanup. The real fixture reindex command indexed 11 chunks in `knowledge-chunks-v1-000011`.
- Prompt integrity evidence: `scripts/verify-prompt-integrity.sh` passed all 13 archived phase prompts after repairing the P01/P02 ledger hashes; `make verify` now runs this gate.
- P11 limits: semantic quality and retrieval evaluation remain later work; the FastEmbed adapter is local and real but does not constitute a quality benchmark. P11 does not implement user query retrieval, permission scope resolution, reranking, evidence resolution, or generation.

## P12 permission-first retrieval baseline

- `knowledge_system.application.retrieval.PermissionFirstRetrievalService` resolves the current OpenFGA-backed `can_view` scope before query embedding or either search branch. An empty or failed scope never becomes an unfiltered query.
- `AuthorizationFilter` and `EffectiveSearchFilter` are immutable typed values. Tenant and trusted resource constraints are mandatory; client-facing constraints are bounded account, department, and UTC update-time narrowers with no raw OpenSearch DSL.
- OpenSearch BM25 and vector candidate methods use the same filter and request an allowlisted metadata-only `_source`; text and vectors are excluded. Index metadata remains defense-in-depth, not authorization truth.
- RRF is deterministic and configurable. Every fused resource is fine-checked with current authorization before a `RetrievalCandidate` is constructed. Returned candidates carry provenance and an authorization decision/fingerprint but no text-bearing field.
- `RetrievalResult.evaluation_record()` exposes ranked IDs, component diagnostics, authorization fingerprint, and the explicit unauthorized-context rate for later retrieval-only evaluation.
- P12 evidence: `make verify` passed with 93 backend unit tests at 91.59% domain coverage, 13 frontend tests at 98.87%, 4 integration tests passed with 8 skips, and 49 security tests passed with 5 skips. The new live OpenSearch filter test was not run because Docker access/private endpoint was unavailable in this session.
- P12 commits: `a927cb9` (`feat(P12): implement permission-first hybrid retrieval`), `fb10e3d` (`fix(P12): stabilize local verification gates`), and `51d68bf` (`docs(P12): record retrieval checkpoint`) are pushed to `origin/master`.

## P13 reranking and evidence-resolution baseline

- `EvidenceResolutionService` consumes only P12 `RetrievalResult` candidates, re-checks current `can_view` before text loading, validates content-store identity/tenant/version matches, and fails closed on authorization or content-store errors.
- `LocalPairwiseReranker` is a bounded local pair scorer and cannot retrieve, enumerate, or admit candidates. Explicit timeout/unavailable/invalid-ID paths retain the already-authorized P12 order with an internal fallback marker.
- `DeterministicEvidenceResolver` relies on typed trusted `EvidencePolicyMetadata`, never source text or a model, for authority, effective time, lifecycle, status, conflict, and lineage policy. It keeps relevance and authority decisions separate.
- `EvidencePacket` holds a stable evidence identity, sanitized text, source locator/URL, timestamps, source/version/authority/freshness/status, classification/shareability, annotations, authorization fingerprint, and trace-only ranking reasons.
- P13 evidence: `make verify` passed with 100 backend unit tests at 90.42% domain coverage, 13 frontend tests at 98.87%, 4 integration tests passed with 8 skips, and 56 security tests passed with 5 skips.
- P13 commits: `9fca6df` (`feat(P13): add evidence resolution`) and `c7f5a4a` (`docs(P13): record evidence checkpoint`) are pushed to `origin/master`.

Next authorized phase: P14 only after an explicit P14 prompt.
