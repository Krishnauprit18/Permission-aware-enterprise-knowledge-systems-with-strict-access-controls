# ADR-016: Grounded Local Generation Uses Structured Drafts And Backend Citations

- Status: `accepted`
- Date: 2026-09-14
- Owners: product and security engineering
- Related phase: P14

## Context

P13 produces authorized, sanitized, authority/freshness-aware evidence packets.
A local answer model can still invent citations, obey source prompt injection,
misrepresent tentative material, or disclose model/runtime failure details.

## Decision

P14 accepts only a P13 `EvidenceResolution` bound to the current authorization
pass. The context builder bounds selected evidence and places retrieved text
only in a delimited untrusted data message. The local Ollama-compatible model
receives no tool interface and returns structured claims, evidence IDs, and
exact supporting quotes.

The backend validates each proposed ID and quote against the selected evidence
package. Citation display metadata is mapped only from backend packets. Invalid
drafts receive one retry; a second invalid citation proposal safely refuses.
Model failures return generic unavailable output. Conflict and freshness/status
qualifications remain deterministic backend metadata.

The local adapter permits only loopback HTTP and externalizes model/runtime
configuration. It is not a cloud fallback.

## Alternatives Considered

- Free-form answer parsing: rejected because it cannot reliably establish
  claim/citation structure.
- Model-generated URLs or titles: rejected because they may be fabricated or
  point at inaccessible resources.
- Treating evidence as a system prompt: rejected because retrieved content is
  untrusted and can carry indirect prompt injection.
- Retrying with broader retrieval after citation failure: rejected because it
  could widen the authorization scope.

## Consequences

The model can be less fluent and may refuse more often, but it cannot add
evidence, change policy, invoke an action, or make a citation eligible. A live
local-runtime acceptance test and durable generation-trace schema wiring remain
explicit follow-up work.
