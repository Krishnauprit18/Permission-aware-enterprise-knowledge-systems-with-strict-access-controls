# ADR-001: Authorization Before Model Context

- Status: `accepted`
- Date: 2026-09-13
- Owners: product and security engineering
- Related phase: P01

## Context

The system handles fragmented enterprise content with different tenant, account, department, classification, and relationship permissions. Retrieval scores and model behavior are not security controls. Filtering a generated answer cannot undo disclosure that occurred when an unauthorized chunk was sent to a reranker, model, log, cache, or citation builder.

## Decision

Current authorization is a mandatory boundary before any retrieved chunk can enter reranking, evidence resolution, citation construction, model context, model-facing embedding or analysis flow, answer cache, or external output. Authorization is deterministic, typed, deny-by-default, and fail-closed when identity or policy state is missing or uncertain.

## Alternatives considered

- Filter only the final answer: rejected because intermediate model-facing and observable surfaces can disclose content.
- Filter after ranking: rejected because ranking features and candidate lists can leak protected content and relevance is not authorization.
- Let an LLM decide access: rejected because the model is untrusted and must not make security decisions.

## Security and privacy impact

The boundary must be enforced for lexical, semantic, cache, citation, and fallback paths. Policy freshness, revocation, deletion, tenant scope, and account relationship are first-class inputs. A policy service or protected storage design may be selected later, but it must preserve this contract.

## Evidence and verification

Required future evidence includes full-path canary tests, instrumentation proving unauthorized IDs do not reach model-facing components, tenant/account authorization matrices, policy-failure tests, revocation tests, deletion tests, and cache-isolation tests. See `INV-AUTHZ-001`, `INV-TENANT-001`, `INV-ACL-CHANGE-001`, and `INV-DELETE-001`.

## Consequences

Some queries will refuse or degrade when policy state is unavailable. Authorization-aware filtering must be applied consistently across all retrieval paths and derivatives, increasing design and test effort but keeping the security boundary explicit.
