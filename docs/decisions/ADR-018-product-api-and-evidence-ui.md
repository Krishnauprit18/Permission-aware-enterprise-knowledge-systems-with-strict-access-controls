# ADR-018: Versioned Product API And Evidence-First UI

- Status: accepted for P16
- Date: 2026-09-14

## Decision

Expose a bounded `POST /api/v1/knowledge/query` contract through a typed
`QueryAnswerService` port. Keep the React client presentation-only, with
memory-only OIDC tokens, plain-text rendering, backend-owned citations, and a
provenance view that excludes chain-of-thought.

## Rationale

The existing P12-P15 domain services already define the security boundary. A
small HTTP projection prevents framework details and browser state from
becoming a second authorization implementation. A response envelope makes
refusal, warnings, freshness, conflicts, citations, and trace IDs explicit and
testable.

## Alternatives considered

- Direct browser access to OpenSearch/PostgreSQL/OpenFGA: rejected because it
  would expose credentials and move authorization into an untrusted client.
- Client-side redaction of internal evidence: rejected because unauthorized or
  non-shareable text must not reach a model or external answer path.
- Exposing model reasoning in `Why this answer?`: rejected because provenance
  is sufficient for review and chain-of-thought is not an application output.
- Cookie/BFF authentication in P16: deferred because the accepted P05 local
  browser flow uses PKCE and memory-only bearer transport. A future cookie
  mode requires CSRF and a shared session store.

## Consequences

The API fails closed when no query composition service is injected. This keeps
the boundary honest while the live P12-P15 composition is completed. Contract
tests use typed injected answers and must not be mistaken for live retrieval or
model acceptance.
