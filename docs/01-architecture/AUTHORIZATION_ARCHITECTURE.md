# Authorization Architecture

## 1. Authority and decision points

Keycloak authenticates the human or service principal. OpenFGA is the source of
relationship truth. PostgreSQL is the source of resource lifecycle and revision
truth. OpenSearch filter metadata is a performance aid and defense-in-depth
constraint, never a grant. The application authorization adapter combines these
inputs into deterministic `can_view` and `can_share_externally` decisions.

No client, frontend, search score, source content, model, prompt, or cache may
grant access. Client-supplied account, department, tenant, classification, or ACL
filters are treated as untrusted query constraints and can only narrow a
server-generated authorization filter.

## 2. Relationship vocabulary

P02 reserves these conceptual object types and relations; exact OpenFGA model
syntax and tuple cardinality are deferred to implementation validation:

| Object | Example relationships | Purpose |
|---|---|---|
| `tenant` | `member`, `admin` | Hard organization boundary |
| `department` | `member`, `lead` | Department-scoped access |
| `account` | `owner`, `supporter`, `product_viewer`, `legal_viewer`, `finance_viewer` | Current business relationship to a customer account |
| `resource` | `parent_account`, `parent_department`, `viewer`, `restricted_viewer` | Resource-specific and inherited view access |
| `audience` | `customer_member`, `approved_recipient` | External audience binding |
| `share_policy` | `share_reviewer`, `approved_source` | Separate customer-safe sharing relationships |

Classification remains deterministic metadata evaluated with relationships. An
OpenFGA relation can establish who is related to an object; application policy
also checks tenant, lifecycle state, classification, intended audience, and
policy version. An LLM is never part of this decision.

## 3. Principal and resource context

The server constructs `PrincipalContext` from a validated OIDC session and
server-side mappings. At minimum it contains principal ID, tenant ID, session
authentication context, and correlation ID. Roles and relationships used for
authorization are resolved from current trusted stores rather than accepted from
arbitrary request fields.

`ResourceContext` contains tenant ID, resource/revision ID, optional account and
department, classification, lifecycle state, OpenFGA object ID, source identity,
and policy metadata version. Missing or conflicting security fields deny access.

## 4. Query-time two-stage enforcement

### Stage 1: server-generated coarse scope

The authorization service resolves an `AuthorizationScope` from OpenFGA for the
current principal and action. It contains only server-generated tenant, account,
department, classification ceiling, explicit object IDs or relation-derived
scope tokens, and the authorization model/tuple version needed for auditing.

The search adapter translates this scope into OpenSearch metadata filters. User
filters are parsed through an allowlist and intersected with this filter using
logical `AND`; they cannot replace or widen it. Tenant ID is mandatory in every
search clause and alias.

### Stage 2: candidate fine check before text

OpenSearch returns `CandidateEnvelope` values containing resource/chunk IDs,
tenant/account metadata, lifecycle/version markers, and lexical/vector scores,
but no chunk text. The authorization service batch-checks each resource against
current OpenFGA relationship truth and PostgreSQL lifecycle state.

Only an allowed candidate is converted into `AuthorizedObjectId`. The search
adapter requires this type to fetch text. The resulting `AuthorizedChunk` carries
the principal/tenant/policy decision token for the request. Reranking, evidence
resolution, context construction, and model adapters accept only authorized
types.

If the coarse filter is stale or over-broad, the fine check still prevents text
fetch. If OpenFGA or lifecycle state is unavailable or inconsistent, the candidate
is denied. If a candidate changes after the check, revision/policy binding fails
the fetch and requires a new decision.

## 5. Security type boundary

The architecture distinguishes these types even when their runtime
representation is small:

```text
CandidateEnvelope       # IDs, metadata, scores; no text
AuthorizedObjectId      # request-bound proof of current can_view decision
AuthorizedChunk         # text fetched only through AuthorizedObjectId
ResolvedEvidence        # authorized chunk plus authority/freshness result
EvidencePackage         # immutable model context with supplied evidence IDs
ValidatedAnswer         # claims/citations validated against the package
ShareApprovedAnswer     # audience-bound external output
```

Constructors for authorization-bearing types are internal to the authorization
and content-fetch boundary. General adapters cannot cast or deserialize them
from client input.

## 6. Dynamic revocation

- OpenFGA relationship updates are authoritative immediately after successful
  write/read consistency according to the configured consistency policy.
- The initial architecture has no cross-request authorization scope cache.
- If a cache is later introduced, it must bind principal, tenant, action,
  OpenFGA model/tuple version, and expiry; change events must invalidate it.
- Every query obtains current scope and every candidate receives a current fine
  check before text fetch.
- Embeddings contain only content-derived vectors, so relationship changes do
  not require re-embedding.
- A stale OpenSearch coarse field can reduce recall after a grant but cannot
  cause disclosure after revocation because fine checks are authoritative.

The required test revokes a role or account relationship while chunks remain in
OpenSearch, executes the next query, and instruments every text-bearing boundary
to prove the revoked chunk never reaches reranking, evidence resolution, context,
LLM input, citation validation, response, or cache.

## 7. External sharing

`can_share_externally` is evaluated for a specific principal, external audience,
tenant/account, evidence-derived claim, classification, and policy version. It
does not reuse `can_view` as an allow result. Internal answers and external
answers use separate cache namespaces and audit actions. A denied share returns
a generic refusal or approved redaction without exposing the hidden source.

## 8. Failure and audit contract

Authorization outcomes are `ALLOW`, `DENY`, or `INDETERMINATE`; only `ALLOW`
permits transition to an authorization-bearing type. Every protected-path error,
timeout, missing relation, tenant mismatch, lifecycle conflict, stale decision,
or unknown classification becomes `DENY`/`INDETERMINATE` and fails closed.

Audit events include decision/action, principal/tenant, object IDs where safe,
policy model/version, reason code, correlation ID, and duration. They exclude
raw chunk text, token contents, complete prompts, and denied resource details in
user-visible output.

## 9. P06 OpenFGA implementation baseline

P06 implements the reserved model as `authorization-model-v1` with these object
types: `user`, tenant, group, department, account, project, and resource. Group
membership is represented as `group:<tenant>-<name>#member`; tenant membership,
department membership, account roles, project inheritance, direct viewer/owner
grants, restricted viewers, and share reviewers are relationship tuples. The
resource relation `can_view` combines direct, owner, account, department, and
project paths. A resource marked restricted by trusted metadata is checked only
through its explicit `restricted_viewer` path. `can_share_externally` is a
separate OpenFGA relation and is additionally bounded by trusted
`PUBLIC`/`CUSTOMER_SHAREABLE` metadata.

`OpenFGAAdapter` is the application-facing policy enforcement point. For an
object check it first validates that the object exists in the server-owned
metadata store, matches the principal tenant, and satisfies local
classification policy; it then checks current tenant membership and the
relationship in OpenFGA with `HIGHER_CONSISTENCY`. The principal's OIDC group
claims are identity context only and are never converted into authorization by
the client or adapter. The adapter also verifies the OpenFGA `tenant` relation
from the resource to the principal's tenant, preventing a relationship graph
mistake from relying on the metadata catalog alone.

Permission-first listing calls OpenFGA `list-objects` for metadata-only resource
IDs, discards unknown or cross-tenant IDs, and rechecks restricted resources
before returning the scope. An empty scope is a valid deny result. An OpenFGA
transport, response, or timeout failure raises `AuthorizationUnavailable` for
scope construction or returns `INDETERMINATE`/deny for an object check; neither
path can produce an allow.

P06 uses `authorization-model-v1`, `tuples-v1`, and `policy-v1`. Each decision
also carries a SHA-256 decision fingerprint over the principal, tenant,
relation, object, outcome, and these versions. The fingerprint contains no
relationship graph details and is intended to bind future cache entries. Tuple
updates must advance the tuple version or emit an equivalent invalidation event
before any authorization cache is introduced.
