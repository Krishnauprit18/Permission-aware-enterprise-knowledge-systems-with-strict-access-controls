# ADR-002: View and External Share Are Separate Decisions

- Status: `accepted`
- Date: 2026-09-13
- Owners: product and security engineering
- Related phase: P01

## Context

An employee may need to read confidential internal material to prepare a customer response, while the customer may receive only approved public or customer-shareable facts. A view permission is therefore not an external disclosure permission.

## Decision

The policy vocabulary contains separate decisions: `can_view` for internal product access and `can_share_externally` for a specific external audience, account, answer, and evidence-derived field. The share decision is evaluated only after view authorization and before export or delivery. It may allow, deny, redact, or require review. Classification labels are inputs to policy, not model decisions.

## Alternatives considered

- Treat every viewable resource as shareable: rejected because internal, confidential, and restricted content would be overshared.
- Treat classification alone as the share decision: rejected because audience, account relationship, redaction, and current policy also matter.
- Generate freely and redact after delivery: rejected because external delivery must be blocked or transformed before release.

## Security and privacy impact

Internal and external paths require separate audit outcomes, cache scopes, citation policies, and refusal behavior. The system must not reveal denied share details to an external recipient.

## Evidence and verification

Test each classification and persona against internal view, customer audience, unrelated customer audience, and restricted audience. Assert `can_view = true` never automatically yields `can_share_externally = true`, and assert redaction/refusal is recorded without leaking hidden content.

## Consequences

Answer generation and export have an additional policy step and may produce different internal and customer-safe responses. This creates clearer product behavior and safer reuse of internal evidence.
