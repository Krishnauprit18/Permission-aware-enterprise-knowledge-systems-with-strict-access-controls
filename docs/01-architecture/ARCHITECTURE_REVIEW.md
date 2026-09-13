# P02 Architecture Review

- Review date: 2026-09-13
- Scope: reference architecture, pipelines, authorization, ports/import rules,
  versioning, and ADR-005 through ADR-010
- Result: `PASS` for architecture-documentation scope

## Security invariant review

| Invariant or threat | Architectural control | Required later evidence | P02 status |
|---|---|---|---|
| `INV-AUTHZ-001` / T-04 | Metadata-only candidates, current OpenFGA fine check, authorized ID required for text fetch, authorized types accepted by reranker/context/LLM | Instrumented canary and boundary tests | Designed; not implemented |
| `INV-TENANT-001` | Server-bound tenant in principal, mandatory tenant filter/alias, fine check, tenant on every derivative | Cross-tenant ingestion/search/cache tests | Designed; not implemented |
| `INV-CITE-001` / T-21 | Server-issued evidence IDs and deterministic citation validator against immutable evidence package | Fabricated/stale/unauthorized ID tests | Designed; not implemented |
| `INV-REFUSAL-001` / T-16 | Generic user response, minimized reason-coded audit, no protected counts/IDs | Existence/timing probe suite | Designed; timing budget deferred |
| `INV-ACL-CHANGE-001` / T-18 | OpenFGA relationship truth, request-local scope, fine check before text, content-only embeddings | Next-query revocation test without re-embedding | Designed; consistency mode deferred |
| `INV-DELETE-001` / T-18 | Immediate `deletion_pending` deny, derivative tombstone/removal, cache invalidation, tuple removal, reconciliation | Delete/de-permission race and resurrection tests | Designed; exact bound deferred |
| `INV-PROMPT-001` / T-08 | Untrusted delimited evidence, no model credentials/tools/policy authority, output validation | Indirect injection corpus at every source type | Designed; not implemented |
| `INV-SHARE-001` / T-10 | Separate audience-bound share decision after internal view authorization | Classification/audience matrix and redaction/refusal tests | Designed; not implemented |
| T-12 logging leakage | OpenTelemetry correlation plus separate minimized audit port; no raw context by default | Secret/classification canary scan | Designed; backend selection deferred |
| T-13/T-14 parser and attachment risk | Raw quarantine, supported types, parser resource/network bounds, explicit failure | Malformed/polyglot/archive/SSRF suite | Designed; parser technology deferred |
| T-15 cache leakage | No initial cross-request query/auth cache; mandatory invalidation port for future use | Persona/tenant/revocation cache tests | Designed; Redis explicitly deferred |
| T-17 supply-chain provenance | Pinned dependencies/images, release manifest, source/build provenance and digests | SBOM, lockfile, image and provenance checks | Designed; implementation tooling deferred |

## Pipeline ordering review

- Ingestion includes every mandated stage in order and checkpoints only after
  consistent required writes.
- Query authenticates and resolves current scope before search, fine-checks IDs
  before text fetch, and permits only authorized types beyond that boundary.
- Deletion marks the resource ineligible during detection, then removes or
  tombstones derivatives, invalidates caches, removes relations, and audits.
- Role changes update OpenFGA first; the next request resolves new scope without
  re-embedding content.

## Dependency and deployment review

- Domain/application code is independent from FastAPI and infrastructure SDKs.
- Adapters cannot call one another or bypass application orchestration.
- The frontend and model containers hold no direct data-store or OpenFGA
  credentials.
- Docker Compose is the only selected deployment topology; no Kubernetes or cloud
  artifacts are introduced.
- Redis has no initial use and is not part of the selected topology.

## Deferred validation risks

- OpenFGA object enumeration, consistency settings, and tuple cardinality need a
  measured prototype before schema lock.
- OpenSearch metadata filter cardinality, hybrid fusion, index aliases, and text-
  free candidate behavior need contract/integration tests.
- Cross-store ingestion/deletion atomicity is a saga/reconciliation problem; the
  exact state machine and recovery protocol remain for implementation design.
- Local model artifacts, parser libraries, dimensions, chunking, and resource
  limits require evaluation and security evidence.
- Timing/existence leakage and update/deletion bounds need measurable thresholds.

No issue found requires weakening an invariant. No business implementation was
added in P02.
