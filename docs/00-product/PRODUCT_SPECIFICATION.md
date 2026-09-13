# Product Specification

- Product: Permission-Aware Enterprise Knowledge System
- Phase: P01
- Status: normative product contract; no feature implementation in this phase
- Deployment posture: local-only, on-prem style
- Scenario: synthetic B2B software company

## 1. Product intent

Northstar Cloud Systems is a fictional B2B software company that sells workflow automation to enterprise customers. Its internal knowledge is split across customer records, product material, engineering operations, legal documents, finance records, support work, and meeting history. The product gives an authenticated Northstar employee a useful answer only from evidence that the employee is authorized to view and that the answer is permitted to share with the requested audience.

The system optimizes for trustworthy answers, not maximum answer rate. It must say that accessible evidence is insufficient when it cannot answer safely. A fluent answer without authorized, attributable evidence is a product failure.

## 2. Scope and tenant model

Northstar is the primary synthetic organization tenant. Its customer accounts are relationship-scoped subdomains, not separate authorization domains. Every source, resource, chunk, embedding, cache entry, trace, and answer has an immutable `tenant_id`; account scope is an additional constraint within the tenant. Security fixtures also include an unrelated synthetic tenant, Harbor Labs, to prove that a Northstar principal cannot retrieve Harbor Labs content and vice versa.

The system must preserve isolation at ingestion, storage, indexing, candidate generation, reranking, evidence resolution, answer generation, caching, export, and observability boundaries. A tenant or account label supplied by a user is a query hint, never an authorization grant.

## 3. Synthetic organization

### Departments

- Sales / Customer Success: account ownership, renewals, adoption, and customer communication.
- Product: roadmap, product requirements, release notes, and product decisions.
- Engineering: incidents, runbooks, technical investigations, and support engineering.
- Legal: contracts, obligations, privacy reviews, and privileged legal analysis.
- Finance: invoices, credit status, revenue operations, and pricing approvals.

### Customer accounts

- Acme Retail: retail operations customer using workflow automation for store replenishment.
- Beacon Health: healthcare-sector customer using workflow automation for scheduling operations. All data is synthetic and contains no real patient data.
- Cedar Logistics: logistics customer using workflow automation for shipment exception handling.

### User personas

| Persona | Department | Typical relationship | Baseline view scope | External sharing posture |
|---|---|---|---|---|
| Maya Rao, Account Manager | Sales / Customer Success | Owns Acme Retail | Assigned-account records, approved customer material, and permitted internal account context | May prepare customer-safe content, but policy still decides each external share |
| Leon Fischer, Product Manager | Product | Product-wide | Product records, release material, aggregate feedback, and explicitly granted account context | Customer sharing requires shareability policy and account context |
| Priya Nair, Support Engineer | Engineering | Supports Beacon Health and Cedar Logistics | Assigned tickets, technical threads, call transcripts, and relevant runbooks | May share only approved, redacted customer-safe material |
| Ada Okafor, Legal Counsel | Legal | Cross-account legal oversight | Explicitly granted contract, policy, and legal records, including high classifications | Legal view permission never implies external sharing permission |
| Tomas Silva, Finance Analyst | Finance | Finance operations | Finance records and explicit account grants | Finance records are not externally shareable by default |

These are examples of policy inputs, not hard-coded authorization rules. A later authorization design must model current role, department, account relationship, explicit grants, resource policy, tenant, and policy version.

## 4. Content inventory

At least five heterogeneous source types are represented in the synthetic dataset:

| Content type | Example | Required provenance and lifecycle fields |
|---|---|---|
| Document | Acme implementation plan or product release note | Source system, source resource ID, revision, author, effective time, superseded/deleted state |
| Support ticket | Beacon incident ticket with comments and status changes | Ticket ID, account, requester, assignee, event times, status history, attachments, deletion state |
| Slack-style message/thread | Engineering thread discussing a Cedar integration failure | Channel/thread/message IDs, participants, account or department scope, sent/edited time |
| Call transcript | Customer success call about an Acme renewal blocker | Call ID, participants, account, recording/transcript revision, call time, retention/deletion state |
| Internal policy | Finance approval policy or legal data-handling policy | Policy ID, owner, effective date, expiry, revision, supersedes relation, classification |

Every canonical resource and derived chunk must retain at least:

- `tenant_id` and optional `account_id`;
- `source_type`, `source_system`, stable source/resource/revision identifiers, and source locator;
- department, owner or accountable team, and authorship/participants where available;
- source-created, source-updated, ingested, effective, expiry, superseded, and deleted timestamps as applicable;
- classification level and machine-readable view/share policy references;
- access-control version or equivalent policy freshness marker;
- parent resource, chunk ordinal, content hash, and derivation lineage;
- lifecycle state and deletion/tombstone evidence.

## 5. Classification and policy vocabulary

Classification is source policy metadata, not an LLM inference. The system may normalize trusted source labels into this fixed vocabulary, but a model must never decide a security classification.

| Level | Meaning | Default view behavior | Default external share behavior |
|---|---|---|---|
| `PUBLIC` | Safe for broad authenticated Northstar use and approved public references | Authenticated same-tenant users may view, subject to tenant policy | Potentially shareable, but still subject to audience and policy checks |
| `CUSTOMER_SHAREABLE` | Intended for a named customer or approved customer audience | Users with valid tenant/account relationship may view | Shareable only to the named/approved customer audience and only when policy permits |
| `INTERNAL` | Northstar internal business information | Explicit internal business permission required | Deny by default |
| `CONFIDENTIAL` | Sensitive business, account, financial, legal, or technical information | Explicit need-to-know grant required | Deny by default; redaction/review may be required |
| `RESTRICTED` | Highest-sensitivity or privileged information | Explicit named or role-based grant, with fail-closed evaluation | Never share by default; normally prohibited without a separate approved decision |

`can_view` answers: "May this authenticated principal receive this resource or derived chunk in the internal product?" `can_share_externally` answers: "May this specific answer or evidence-derived field be sent to this external audience?" They have different inputs, different audit events, and different failure behavior. `can_view = true` never implies `can_share_externally = true`.

## 6. Functional requirements

| ID | Requirement | Acceptance condition |
|---|---|---|
| FR-AUTH-001 | Authenticate every interactive request | Unauthenticated or invalid sessions cannot query, inspect citations, or access traces |
| FR-AUTHZ-001 | Authorize before evidence enters downstream model flow | Unauthorized chunks are removed before reranking, prompt construction, citation construction, or any LLM call |
| FR-AUTHZ-002 | Enforce tenant and account scope | No query can retrieve another tenant; account relationship and resource policy are checked independently |
| FR-AUTHZ-003 | Keep view and external share decisions separate | Internal answer and customer-safe export use separate policy decisions and traces |
| FR-INGEST-001 | Ingest heterogeneous sources | Documents, tickets, messages/threads, call transcripts, and policies preserve provenance and lifecycle state |
| FR-INGEST-002 | Parse and chunk with lineage | Every chunk maps to one parent revision, stable evidence ID, metadata set, and content hash |
| FR-RETRIEVE-001 | Provide hybrid retrieval | Lexical and semantic candidate paths can be evaluated independently and together; both honor authorization |
| FR-RETRIEVE-002 | Rerank only authorized candidates | Reranking never receives an unauthorized candidate, even transiently |
| FR-EVIDENCE-001 | Resolve authority, freshness, and conflicts | Results preserve competing evidence and apply documented resolution or refusal rules |
| FR-ANSWER-001 | Generate grounded answers | Answer claims map to supplied evidence IDs; unsupported claims are omitted or qualified |
| FR-ANSWER-002 | Validate citations | A citation is accepted only when its ID was supplied in the authorized evidence set and its referenced span is valid |
| FR-SHARE-001 | Enforce customer-safe output | External output is separately checked, redacted or refused, and never uses view permission as a proxy |
| FR-TRACE-001 | Emit an auditable trace | Trace records principal, policy version, query, candidate decisions, evidence IDs, answer/citation validation, and outcome without raw sensitive content by default |
| FR-UPDATE-001 | Apply hourly source updates | A successful source update becomes eligible for the documented freshness bound and carries revision lineage |
| FR-UPDATE-002 | Apply ACL changes without re-embedding | Revocation affects the next authorized query while content embeddings remain content-derived rather than permission-derived |
| FR-DELETE-001 | Propagate source deletion/de-permissioning | Searchable derivatives, citations, caches, and future answers cannot use deleted or de-permissioned content after the defined bound |
| FR-EVAL-001 | Separate retrieval and generation evaluation | Retrieval metrics do not hide behind answer quality; both have independent fixtures and reports |

## 7. Answer contract

An internal answer contains a concise response, uncertainty or conflict qualification when needed, and citations to stable evidence IDs. It must not expose inaccessible resources through wording, citation labels, counts, or error details. A refusal uses a generic safe response such as "I do not have enough accessible evidence to answer that." The exact response may vary, but it must not confirm the existence, classification, owner, or contents of an inaccessible resource by default.

The answer path is ordered as follows at the contract level: authenticate principal; obtain current policy context; retrieve only candidates within tenant and view scope; rerank authorized candidates; resolve evidence; construct an authorized evidence package; generate; validate claims and citations; apply external-share policy when relevant; emit redacted trace. A later implementation may optimize this sequence only if it preserves the same security boundary.

## 8. Freshness, conflict, and update obligations

- Source synchronization runs on a realistic hourly cadence for the demo and records lag, revision, and failure state.
- A role or account-relationship revocation must affect the next authorized query within the documented authorization-cache bound, without requiring content re-embedding.
- A source deletion or de-permissioning event must invalidate the canonical resource, chunks, search candidates, citation eligibility, and relevant answer caches within a documented deletion bound.
- Newer effective policy or source revisions supersede older records when the authority rules say so; superseded evidence remains traceable but is not silently presented as current.
- If equally authoritative evidence conflicts, the system identifies the conflict or refuses rather than inventing a resolution.

## 9. Non-functional requirements

- Local-only operation with explicit, reviewable boundaries for any model process or connector.
- Strictly typed contracts and deterministic policy decisions.
- Secure defaults, deny-by-default authorization, fail-closed protected paths, and redacted structured logging.
- Reproducible ingestion, retrieval, answer validation, and evaluation traces.
- No secret material in source, fixtures, prompts, logs, citations, or evidence reports.
- Observable authorization decisions and invalidation lag without logging protected content.
- Graceful degradation: unavailable sources or models produce a bounded failure or refusal, never an authorization bypass.

## 10. Explicit non-goals for P01

P01 does not select programming languages, databases, vector indexes, model runtimes, identity protocols, deployment manifests, parser libraries, or ranking algorithms. Those choices require architectural comparison in later phases. P01 also does not implement authentication, ingestion, retrieval, generation, storage, or tests beyond documentation checks.
