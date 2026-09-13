# ADR-006: OpenFGA for Relationship Authorization

- Status: `accepted`
- Date: 2026-09-13
- Owners: architecture and security engineering
- Related phase: P02

## Context

Authorization depends on tenant membership, department, customer-account
relationship, role, explicit resource grants, inheritance, classification, and
external audience. Role or relationship revocation must affect the next query
without changing content embeddings.

## Decision

Use OpenFGA as the source of relationship truth. The application resolves current
server-owned authorization scope at query time, builds coarse search filters,
and fine-checks candidate objects before text fetch. `can_view` and
`can_share_externally` are separate application decisions backed by explicit
relationships and deterministic metadata/lifecycle policy.

OpenFGA model IDs and relevant consistency/freshness context are versioned and
recorded in audit events. Client relationship claims, search filters, and model
output cannot grant access.

## Alternatives considered

- Hard-coded application RBAC: rejected because account/resource relationships,
  inheritance, and dynamic revocation exceed a static role matrix and tend to
  spread policy across handlers.
- ACL tables evaluated only in PostgreSQL: viable, but not selected because a
  dedicated relationship model provides clearer policy semantics, model
  versioning, and testable relation checks.
- Authorization inferred from search metadata: rejected because indexed metadata
  can be stale and search relevance is not permission.
- LLM-assisted authorization: rejected because security decisions must be
  deterministic and independently testable.

## Security and privacy impact

OpenFGA unavailability or ambiguous results fail closed. Request-local scope is
the initial default; any future cache must be policy-versioned and invalidated.
PostgreSQL lifecycle state is checked with relations so deleted content cannot
be recovered through a stale tuple.

## Evidence and verification

Required tests include persona/account/classification matrices, cross-tenant
denial, direct object checks, inherited relations, role and relationship
revocation, policy-model migration, indeterminate failure, stale coarse-filter
defense, and separate share decisions.

## Consequences

The system adds a local authorization service and policy model lifecycle. In
return, relationships remain independent from embeddings and source content,
allowing next-query revocation and centralized review.
