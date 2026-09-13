# Standards Verification Matrix

This matrix defines planned engineering verification guidance. It does not claim certification, accreditation, compliance, or complete coverage. A future implementation phase must attach each applicable requirement to code, test, configuration, and dated evidence; exact control-level selections that depend on the architecture are intentionally deferred.

## Reference versions

| Reference | Version/baseline | Official reference |
|---|---|---|
| NIST Secure Software Development Framework | SSDF 1.1, NIST SP 800-218 | [NIST SSDF project](https://csrc.nist.gov/projects/ssdf) |
| OWASP Application Security Verification Standard | ASVS 5.0.0 | [OWASP ASVS project](https://owasp.org/projects/asvs) |
| OWASP Top 10 | 2025 | [OWASP Top 10:2025](https://top10.owasp.org/2025/) |
| OWASP Top 10 for LLM Applications | GenAI/LLM Top 10 2026 | [OWASP GenAI LLM Top 10 2026](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/) |
| SLSA | 1.2 concepts | [SLSA specification 1.2](https://slsa.dev/spec/v1.2/) |

## Cross-cutting evidence obligations

- Every security requirement has an owner, an implementation reference, a test or review method, and a dated result.
- Security-sensitive metadata and decisions have explicit provenance and policy-version evidence.
- Required checks fail the phase or merge when evidence is missing, a protected path fails open, or a regression is found.
- Standards references are rechecked before release; version changes create a documented review item rather than silently changing the baseline.

## Product and threat coverage

| Product area | Planned evidence | P01 source |
|---|---|---|
| Authentication and session binding | Identity/session threat tests, invalid-session tests, privileged-action audit evidence | FR-AUTH-001; T-01 |
| Tenant and account isolation | Cross-tenant/account authorization matrix; model-boundary canary tests; cache tests | FR-AUTHZ-001/002; INV-TENANT-001; T-04/T-06/T-15 |
| View versus external share | Separate policy decision tests for internal, customer, and restricted audiences; redaction/refusal evidence | FR-AUTHZ-003; T-10 |
| Ingestion, parsing, attachments | Connector path/type/size/hash/duplicate checks, provenance, retry/checkpoint ordering, source-aware parser bounds, Unicode/active-content handling, ACL/classification propagation, locator reconstruction, SSRF, malformed-file, attachment quarantine, and deletion tests | FR-INGEST-001/002; T-07/T-13/T-14/T-42/T-43/T-44/T-45/T-46/T-47/T-48 |
| Embeddings and search index | Offline-provider tests, bounded batches/timeouts/retries, model/version/dimension checks, strict BM25/vector mapping, alias cutover, metadata propagation, deletion, and private-endpoint tests | FR-RETRIEVE-001/002; T-04/T-11/T-15/T-19/T-49/T-50/T-51 |
| Retrieval, reranking, and vectors | Lexical/semantic isolation tests, pre-rerank authorization instrumentation, vector-probing tests | FR-RETRIEVE-001/002; INV-AUTHZ-001; T-04/T-19 |
| Authority, freshness, and conflict | Revision, effective-time, supersession, poisoning, and refusal fixtures | FR-EVIDENCE-001; T-09 |
| Grounded generation and citations | Claim-to-evidence validator tests, fabricated-ID tests, malformed-output tests, refusal tests | FR-ANSWER-001/002; INV-CITE-001; T-08/T-20/T-21 |
| Prompt-injection resilience | Direct and indirect injection corpus, source-text delimiting, no-policy-change assertions | INV-PROMPT-001; T-08 |
| Revocation, updates, deletion | Bounded lag tests for hourly updates, ACL changes, de-permissioning, deletion, derivatives, and caches | FR-UPDATE-001/002; FR-DELETE-001; T-15/T-18 |
| Traces and logs | Structured schema, redaction, access-control, secret-scan, and canary tests | FR-TRACE-001; T-03/T-12 |
| Local operations and supply chain | Dependency review, SBOM, artifact integrity, source/build provenance, restore and rollback evidence | T-05/T-11/T-17 |
| Synthetic dataset integrity | Deterministic fixture validation, source-hash checks, tenant/ACL/lifecycle/lineage validation, required scenario coverage, and synthetic-content safety checks | P08; T-40/T-41 |

## NIST SSDF 1.1 mapping

The project will use SSDF 1.1 as a secure-development vocabulary. Planned evidence is mapped at practice level until the implementation stack is selected:

| SSDF 1.1 practice area | Planned verification in this project |
|---|---|
| Prepare the Organization (PO) | Maintain this constitution, product security requirements, threat model, risk register, ownership, dependency policy, and phase gates. |
| Protect the Software (PS) | Protect source/configuration, review changes, control release inputs, retain release evidence, and collect source/build provenance. |
| Produce Well-Secured Software (PW) | Use the threat model and ADRs in design; implement typed boundaries, secure defaults, authorization tests, parser limits, output validation, and security testing. |
| Respond to Vulnerabilities (RV) | Record findings, severity, remediation, regression tests, verification, and residual risk using the security finding template. |

Evidence to collect: requirements-to-test traceability, threat-model review, ADRs, code review, dependency/secret scans, test reports, SBOM, vulnerability records, release provenance, and rollback evidence. This is an alignment plan, not a claim that SSDF practices have already been satisfied.

## OWASP ASVS 5.0.0 mapping

ASVS 5.0.0 is the detailed application verification reference. The future implementation must pin exact requirement IDs during architecture and map them to tests. Current planned coverage is:

| ASVS focus | Planned project verification |
|---|---|
| Architecture, validation, and business logic | Typed request/resource contracts; trust-boundary review; deny-by-default policy; no user-controlled authorization claims; injection tests. |
| Authentication and session management | Authenticated request tests, session lifecycle tests, replay/expiry handling, and tenant-bound principal context. |
| Authorization and access control | Object/function/field-level checks, account and tenant isolation, fail-closed policy failure, revocation, and separation of `can_view` from `can_share_externally`. |
| API/service and error handling | Safe errors, generic refusal behavior, input limits, output schemas, no sensitive status/count leakage, and exceptional-condition tests. |
| File handling and SSRF | Source allowlists, attachment quarantine, parser isolation, type/size/depth limits, and malicious-file tests. |
| Data protection and cryptography | Secret handling, data minimization, protected metadata, key/configuration review, and cache/backup access controls. |
| Logging and monitoring | Structured redacted audit events, operator authorization, integrity, retention, and log-canary tests. |
| Configuration and dependency security | Secure defaults, pinned lockfiles, migration review, SBOM, vulnerability scanning, and provenance verification. |

### P05 authentication verification

| Authentication property | Project verification |
|---|---|
| Authorization Code + PKCE | Frontend constructs a public-client code request with S256, binds callback state, and keeps the verifier transient. |
| Access-token validation | Backend tests signature/key selection, RS256 allowlist, issuer, audience, required claims, expiry, not-before, issued-at, and explicit 0-300 second clock skew. |
| Principal boundary | `/api/v1/auth/me` returns only the validated subject, tenant, and groups; no client-provided claim or tenant selector grants resource access. |
| Session lifecycle | Logout revokes a validated sid/jti handle in the local process, browser memory is cleared, and reuse is rejected until expiry. |
| Error/log hygiene | Missing and invalid credentials use the same generic 401 response; correlation IDs are fresh server values; allowlisted logs exclude bearer, cookie, claim, and password values. |
| Cookie/CSRF posture | Current bearer transport uses no auth cookie. A future cookie/BFF route is blocked until SameSite/HttpOnly/Secure, CSRF, origin, rotation, and invalidation tests exist. |

### P06 authorization verification

| Authorization property | Project verification |
|---|---|
| Relationship source | `OpenFGAAdapter` uses OpenFGA `check` and `list-objects`; clients, search metadata, model output, and identity group claims cannot grant access. |
| Tenant isolation | Server-owned resource metadata and a separate current tenant-membership check deny unknown or cross-tenant resources before an allow is returned. |
| Fine-grained inheritance | Model v1 covers account roles, departments, groups, projects, direct viewers/owners, and explicit restricted viewers; restricted resources use the explicit path. |
| View/share separation | `can_view` and `can_share_externally` are independent relations, with trusted classification gating external sharing. |
| Failure closed | OpenFGA transport/status/schema failures return `INDETERMINATE`/deny for checks and raise `AuthorizationUnavailable` for protected scope construction. |
| Revocation and cache versioning | Each request consults current relationship truth; decision and scope fingerprints bind principal, tenant, relation, object/scope, outcome, model, tuple, and policy versions. |
| Safe audit | Decision audit metadata contains action, outcome, reason, versions, correlation ID, duration, and fingerprint without raw graph details or content. |

### P07 persistence verification

| Persistence property | Project verification |
|---|---|
| Migration authority | `backend/migrations/0001_initial.sql` is applied only by the explicit checksum-verified runner; runtime code contains no DDL. |
| Tenant integrity | Tenant-safe foreign keys, source identity uniqueness, version/chunk relationships, and typed repository errors reject mismatched data. |
| Stable identity | `stable_chunk_id()` and immutable version checks support deterministic re-ingestion and citation reconstruction. |
| Lifecycle/deletion | Deleted source items/chunks require deletion timestamps; tombstones carry effective and retention times and are idempotent. |
| Transaction safety | `PostgresUnitOfWork` commits successful operations and rolls back exceptional operations; integration tests assert no partial rows. |
| Secret minimization | Principal rows contain only external identity references; connections contain only secret references; traces store hashes and IDs, not raw queries or context. |

## OWASP Top 10:2025 mapping

| OWASP category | Planned verification |
|---|---|
| A01:2025 Broken Access Control | INV-AUTHZ-001, INV-TENANT-001, revocation/deletion/cache tests, and full authorization matrix. |
| A02:2025 Security Misconfiguration | Secure defaults, fail-closed configuration, no debug leakage, local boundary review, and configuration tests. |
| A03:2025 Software Supply Chain Failures | Lockfiles, dependency review, SBOM, artifact verification, and SLSA-oriented provenance. |
| A04:2025 Cryptographic Failures | Secret/key handling and protected data/configuration review; exact mechanisms deferred to architecture. |
| A05:2025 Injection | Query, template, parser, metadata, output encoding, and model-output handling tests. |
| A06:2025 Insecure Design | Threat model, ADR review, authorization-before-context architecture, deletion/revocation design, and abuse-case evaluation. |
| A07:2025 Authentication Failures | Invalid/replayed/expired session tests, privilege-change tests, and tenant-bound identity checks. |
| A08:2025 Software or Data Integrity Failures | Source lineage, ACL metadata integrity, citation validation, deletion state, dependency and artifact provenance tests. |
| A09:2025 Security Logging and Alerting Failures | Redacted structured audit events, security outcome coverage, protected operator access, and detection evidence. |
| A10:2025 Mishandling of Exceptional Conditions | No silent exception swallowing, bounded dependency failures, fail-closed protected paths, safe refusals, and fault-injection tests. |

## OWASP GenAI/LLM Top 10 2026 mapping

| OWASP category | Planned verification |
|---|---|
| LLM01:2026 Prompt Injection | Indirect injection fixtures in documents, messages, transcripts, and attachments; instruction/data separation; no model authorization. |
| LLM02:2026 Sensitive Information Disclosure | Pre-context filtering, output/share policy, log redaction, cache isolation, refusal non-disclosure, and side-channel tests. |
| LLM03:2026 Excessive Agency | Model has no authorization, arbitrary retrieval, deletion, export, or policy-changing authority; tool-scope tests if tools are later introduced. |
| LLM04:2026 Supply Chain | Model/parser/dependency provenance, artifact verification, lockfiles, SBOM, and replacement detection. |
| LLM05:2026 Data and Model Poisoning | Source provenance, revision/authority/freshness conflict tests, poisoning corpus, and model-asset integrity evidence. |
| LLM06:2026 Unbounded Consumption | Query, parser, retrieval, reranking, and generation budgets; concurrency/backpressure and abuse tests. |
| LLM07:2026 Misinformation | Claim grounding, citation validation, stale/conflicting evidence qualification, refusal thresholds, and separate generation evaluation. |
| LLM08:2026 Hidden Context Exposure | Never expose system instructions, unauthorized chunks, hidden metadata, traces, or other sessions through answers, logs, citations, or model-facing interfaces. |
| LLM09:2026 Vector and Embedding Weaknesses | ACL-independent vector filtering, tenant isolation, derivative deletion, embedding access controls, and probing tests. |
| LLM10:2026 Improper Output Handling | Strict output schema, claim/citation validation, safe rendering/encoding, and malformed/active-content output tests. |

## SLSA 1.2 concepts mapping

SLSA concepts guide source and build provenance. The project does not claim a SLSA level.

| Concept | Planned verification |
|---|---|
| Source provenance | Record reviewed source revision, change identity, review outcome, and relationship between source and phase/release. |
| Build provenance | Record source revision, dependency/material digests, builder/process identity, build parameters, timestamps, and artifact digests. |
| Provenance verification | Verify expected source, dependencies, builder, and artifact identity before release or local deployment; fail the gate on mismatch. |
| Attestation retention | Store provenance and verification evidence with release evidence while excluding secrets and protected source content. |
