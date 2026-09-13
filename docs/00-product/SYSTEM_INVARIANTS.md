# System Invariants

These invariants are normative. Later implementation and evaluation phases must preserve them and attach executable evidence. P01 defines the contracts; it does not implement them.

## Authorization and isolation

### INV-AUTHZ-001: pre-context authorization

An unauthorized chunk is never included in an LLM context. The same exclusion applies before reranking, evidence resolution, citation construction, model-facing analysis, answer caching, export, or any equivalent downstream path.

### INV-TENANT-001: tenant isolation

No cross-tenant content is retrievable. Tenant scope is bound to the authenticated principal by the server and is enforced at ingestion, storage, indexing, candidate generation, ranking, caching, output, and trace boundaries.

### INV-ACL-001: deny by default

Missing, ambiguous, stale, invalid, or unavailable authorization state denies protected access. Relevance, classification text, model confidence, user assertion, or source wording cannot grant access.

### INV-SHARE-001: view/share separation

`can_view` and `can_share_externally` are separate decisions. View permission is required before an answer can use evidence, but it never implies permission to disclose that evidence to an external audience.

## Evidence and model boundaries

### INV-CITE-001: supplied evidence citations only

Citations can only reference supplied evidence IDs. A citation is valid only when its evidence ID and referenced span belong to the authorized evidence package for that query and remain eligible under current lifecycle and policy state.

### INV-PROMPT-001: retrieved text is untrusted

Retrieved text is untrusted data, never an authority source for system instructions. Source content, attachments, metadata, model output, and relevance scores cannot change policy, instructions, classification, or tenant scope.

### INV-EVIDENCE-001: provenance and qualification

Every material claim is grounded in attributable evidence with source and revision lineage. Stale, superseded, conflicting, or insufficiently authoritative evidence is qualified or refused rather than silently presented as current fact.

### INV-LLM-001: no model security decisions

An LLM cannot authenticate, authorize, classify security, broaden retrieval, mint evidence IDs, resolve access conflicts, or approve external sharing. Those decisions remain deterministic application policy.

## Refusal and lifecycle

### INV-REFUSAL-001: refusal non-disclosure

Refusal behavior must not leak sensitive resource existence by default. User-facing responses do not reveal inaccessible resource identifiers, owners, classifications, counts, contents, or existence-specific error details. Authorized traces may retain safe reason codes and stable references needed for operations.

### INV-ACL-CHANGE-001: current authorization after revocation

Role or relationship revocation affects the next authorized query within the documented authorization-cache bound without re-embedding content. Indexed content and embeddings are not permission proof.

### INV-DELETE-001: deletion cascade

Source deletion cascades to searchable derivatives and relevant caches. Deleted or de-permissioned content is ineligible for retrieval, ranking, citation, answer generation, export, and future cached answers within the documented deletion bound.

### INV-UPDATE-001: revision visibility

An accepted hourly source update preserves revision lineage and becomes eligible within the documented freshness bound. Superseded material cannot silently outrank or replace a newer effective authority.

## Operations and observability

### INV-TRACE-001: auditable minimized trace

Security-sensitive decisions produce structured, integrity-protected, access-controlled traces with principal, tenant, policy version, evidence IDs, outcome, and correlation data. Raw restricted content, credentials, and full model context are excluded by default.

### INV-FAIL-001: protected fail closed

Identity, policy, integrity, deletion, evidence validation, dependency, or model failures never bypass protected authorization or shareability controls. The user receives a bounded refusal or error and operators receive an auditable reason.
