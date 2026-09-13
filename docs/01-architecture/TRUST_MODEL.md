# Trust Model

This is a boundary and data-flow model, not an implementation architecture. It deliberately avoids selecting technologies. The model describes what must be trusted for a decision, what must be treated as untrusted, and where authorization must be re-established.

## 1. Security objectives

1. Confidentiality: a principal receives only content and derived output allowed by current tenant, account, department, classification, relationship, and grant policy.
2. Integrity: provenance, ACL state, revisions, deletion state, citations, and trace events cannot be silently altered.
3. Availability: expensive or hostile inputs cannot bypass policy or exhaust the local service beyond defined bounds.
4. Accountability: authorization, evidence selection, answer validation, sharing, update, revocation, and deletion decisions are attributable and reviewable without raw sensitive payloads.
5. Grounding: claims are supported by authorized evidence IDs and stale/conflicting evidence is qualified or refused.

## 2. Actors and trust assumptions

| Actor | Trust level | Allowed capability | Required assumption or control |
|---|---|---|---|
| Authenticated employee | Partially trusted | Submit questions and receive permitted internal answers | Identity is authenticated, but user input is untrusted and cannot grant access |
| External recipient | Untrusted recipient | Receive only an explicitly share-approved answer | Audience/account binding and `can_share_externally` are checked separately |
| Tenant administrator | Privileged human | Manage identities, relationships, source connections, and policy | Privileged actions require strong authentication, least privilege, and audit |
| Source owner | Trusted for source assertions, not for application policy | Publish, revise, or delete source records | Connector validates provenance and treats content body as untrusted data |
| Connector/ingestion worker | Service actor | Fetch and transform configured source data | Scoped credentials, replay protection, parser limits, and failure visibility |
| Authorization policy service | Trusted security component | Evaluate current identity/resource/audience policy | Deterministic, typed, deny-by-default, fail-closed, independently testable |
| Search and ranking components | Untrusted for authorization | Produce candidates or scores | Receive only authorized candidates; scores never grant access |
| LLM/model process | Untrusted decision aid | Transform supplied evidence into a draft answer | Cannot authorize, classify, fetch arbitrary data, or override system instructions |
| Local operator | Privileged infrastructure actor | Run, update, inspect, back up, and recover the system | Operational access is audited and raw protected content is restricted |
| Attacker | Malicious | Attempt unauthorized access, manipulation, injection, leakage, or denial of service | Threat model assumes hostile requests, source content, attachments, and dependencies |

## 3. Assets

- Identity, session, tenant membership, department, role, account relationship, grants, and policy version.
- Raw source resources, revisions, attachments, transcripts, messages, and deletion/tombstone state.
- Parsed documents, chunks, metadata, content hashes, embeddings, lexical terms, ranking features, and caches.
- Authorization decisions, candidate lists, evidence packages, answer drafts, citations, redaction decisions, and external exports.
- Prompt templates, system/developer instructions, model configuration, model inputs/outputs, and local model artifacts.
- Source credentials, encryption material, configuration, migrations, dependency manifests, build artifacts, and provenance evidence.
- Audit traces, security events, metrics, error data, backups, and recovery artifacts.

## 4. Trust boundaries

### TB-1: User or external client to application

Requests, identity claims, audience labels, questions, and export choices are untrusted. The application authenticates the principal and ignores user-supplied claims about permissions.

### TB-2: Identity and authorization boundary

Authenticated identity data and current policy state enter the policy decision point. The policy result is security-sensitive; stale or unavailable policy data fails closed for protected content.

### TB-3: Source systems to ingestion

Connectors cross from source-owned systems into the local knowledge system. Both source metadata and content require validation. Content is data, not instructions.

### TB-4: Ingestion to canonical and derived stores

Parsers, chunkers, embedding services, lexical indexes, and caches create derivatives. Each derivative must retain tenant, scope, classification, lineage, lifecycle, and ACL freshness data.

### TB-5: Retrieval and policy boundary

Candidate generation and reranking are not security authorities. Current authorization must filter before any candidate is exposed to ranking, evidence resolution, citation construction, or model context.

### TB-6: Evidence package to model

The model receives only an explicit, immutable-in-use package of authorized evidence and safe task instructions. Retrieval text is delimited and labeled untrusted. The model cannot add evidence IDs or policy grants.

### TB-7: Model/output to user or external audience

Model output is untrusted. Claim support, citation IDs, classification, shareability, redaction, and audience policy are validated before release.

### TB-8: Application to logs, metrics, backups, and operators

Observability and recovery systems are separate disclosure surfaces. They receive structured, minimized, redacted events and enforce operator authorization.

### TB-9: Dependencies, parsers, and build inputs

Third-party packages, model artifacts, source attachments, configuration, and build tools are supply-chain inputs. Integrity and provenance are verified before use.

## 5. Contract-level data flows

1. Client sends a session-authenticated query and optional intended audience.
2. Authentication resolves a principal bound to one tenant and current policy context.
3. Connectors ingest source revisions and metadata; validation creates canonical resources or rejects them visibly.
4. Parsing and chunking produce lineage-bearing derivatives; policy metadata is carried forward and never inferred by the model.
5. Query orchestration asks lexical and semantic retrieval for candidates constrained by tenant and current view scope.
6. The authorization boundary filters any candidate that is not explicitly viewable. The unauthorized set is discarded before ranking/model-facing components.
7. Authorized candidates are reranked and resolved for authority, freshness, conflict, and sufficiency; an evidence package is formed.
8. The model receives only that package and produces a draft. It cannot fetch, broaden scope, change classification, or mint citations.
9. Validation maps claims only to supplied evidence IDs, applies share policy for external audiences, emits the answer or refusal, and records a minimized trace.

## 6. Trust decisions

- Trusted security inputs: authenticated principal, server-resolved tenant, current policy records, validated source provenance, deletion state, and explicit system instructions.
- Untrusted data: user question, audience labels, source content, message text, transcript text, attachments, model output, retrieval scores, citations proposed by a model, cache contents, and error strings from dependencies.
- No component may derive authorization from relevance, semantic similarity, source wording, model confidence, classification text, or user assertion.
- Every cache key and cache value that can affect retrieval or output is tenant- and policy-aware, with invalidation on ACL and deletion changes.
- A failure of identity, policy lookup, source integrity, evidence validation, deletion processing, or output policy must fail closed for protected output and produce an auditable reason code.
