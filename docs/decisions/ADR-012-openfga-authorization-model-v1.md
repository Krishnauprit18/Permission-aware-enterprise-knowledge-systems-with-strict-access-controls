# ADR-012: OpenFGA Authorization Model v1

- Status: `accepted`
- Date: 2026-09-13
- Owners: application and security engineering
- Related phase: P06

## Context

The system needs tenant isolation, customer-account relationships, department
and group inheritance, direct resource grants, explicit restricted access, and a
separate external-sharing decision. Relationships change independently of
indexed content, so role revocation must affect the next authorization request
without re-embedding content.

## Decision

Use an OpenFGA schema 1.1 model with `tenant`, `group`, `department`, `account`,
`project`, and `resource` objects. Use direct and computed relations for tenant
membership, group membership, account roles, department membership, project
inheritance, resource viewer/owner grants, explicit `restricted_viewer`, and
`share_reviewer`. The resource `can_view` relation provides the relationship
answer for ordinary resources; the application selects `restricted_viewer` for
trusted restricted metadata. `can_share_externally` remains separate and is
allowed only when OpenFGA, trusted classification, and external-share metadata
all allow it.

The backend adapter is the policy enforcement point. It validates the
server-owned resource catalog and tenant membership before accepting an
OpenFGA relationship result, including the resource-to-tenant relation. It uses current high-consistency checks, never
trusts client filters or identity group claims as grants, and fails closed on
unknown, inconsistent, unavailable, or malformed decisions. Permission-first
listing returns only metadata IDs and applies tenant filtering plus restricted
fine checks before the scope can reach future search code.

## Alternatives considered

- Application-only RBAC: rejected because account, department, project, and
  direct resource relationships would become scattered and hard to revoke
  consistently.
- Client-provided ACL filters: rejected because request filters cannot be an
  authorization grant and can be tampered with.
- Search metadata as authority: rejected because indexes can be stale or
  poisoned; metadata is a guard and OpenFGA remains relationship truth.
- Per-resource PostgreSQL ACL checks only: deferred because the relationship
  graph is clearer and more independently testable in OpenFGA; PostgreSQL still
  owns trusted lifecycle/resource metadata.
- LLM-based policy inference: rejected because authorization must be
  deterministic, auditable, and independent of model behavior.

## Security and privacy impact

Tenant membership is checked separately from the resource relationship, and the
resource catalog blocks cross-tenant or unknown objects even if a bad tuple is
present. Decision audit fields contain action, outcome, reason, versions,
correlation ID, duration, and a fingerprint; raw graph details and content are
excluded. OpenFGA outage produces deny/indeterminate behavior rather than
best-effort access.

## Evidence

P06 tests cover account, cross-account, department/group inheritance, direct
restricted grant, relation revocation on the next request, unknown resources,
tenant isolation, separate sharing, list scoping, and authorizer outage. The
local model and tuple seed are under `platform/openfga/`; `make
openfga-bootstrap` is idempotent and does not require secrets.
