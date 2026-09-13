# ADR-009: Local Model Adapter Interfaces

- Status: `accepted`
- Date: 2026-09-13
- Owners: architecture, security, and evaluation engineering
- Related phase: P02

## Context

The system needs language generation, embeddings, and reranking while remaining
local-first. Model artifacts and runtimes will change as quality, hardware,
latency, and licensing are evaluated. Model choice must not leak into business or
authorization logic.

## Decision

Define separate typed `LLM`, `Embedder`, and `Reranker` ports. Default adapters
must run locally. Model names, artifact locations, dimensions, endpoints, limits,
and versions are configuration, never hard-coded business logic. Each request and
evaluation record includes the applicable adapter/model version.

The model process receives only the minimum adapter payload. The LLM cannot
authorize, classify, retrieve arbitrary data, change policy, validate its own
citations, or access infrastructure credentials.

## Alternatives considered

- Direct calls to one model SDK throughout application code: rejected because it
  couples business/security flow to a vendor and weakens test isolation.
- Cloud-only model APIs: rejected as the default because they violate local-only
  operation and expand the data boundary.
- One generic “AI” interface: rejected because embedding, reranking, and
  generation have different inputs, security boundaries, versions, and tests.
- Hard-code one local model: rejected until quality, resource, licensing, and
  evaluation evidence exists.

## Security and privacy impact

Adapters enforce bounded inputs/outputs, timeouts, local endpoint allowlists,
schema validation, telemetry minimization, and no credential propagation. Model
output remains untrusted. Embeddings contain content only, not ACL relationships.

## Evidence and verification

Use fake adapters for deterministic application tests and real local adapters for
contract/evaluation tests. Verify no unauthorized text reaches any adapter,
versions are recorded, malformed output fails safely, and configuration changes
do not alter authorization semantics.

## Consequences

There is modest adapter and configuration overhead. The project gains local
runnability, model portability, independent evaluation, and a narrow security
boundary.
