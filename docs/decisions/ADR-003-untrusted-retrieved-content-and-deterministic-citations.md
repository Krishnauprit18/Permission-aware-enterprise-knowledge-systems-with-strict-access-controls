# ADR-003: Retrieved Content Is Untrusted and Citations Are Server-Validated

- Status: `accepted`
- Date: 2026-09-13
- Owners: product and security engineering
- Related phase: P01

## Context

Source content can contain errors, stale statements, malicious instructions, or text crafted to manipulate an LLM. A model may also invent evidence IDs or cite an inaccessible, deleted, or superseded resource.

## Decision

Retrieved text is delimited and treated as untrusted data, never as system instruction, authority, policy, or permission. The application constructs the authorized evidence package and owns stable evidence IDs. The model may draft claims and citation proposals, but a deterministic validator accepts only claims supported by supplied evidence IDs and valid spans. Authority, freshness, conflict, classification, and shareability remain application policy decisions.

## Alternatives considered

- Trust source wording as instructions: rejected because source content crosses an untrusted boundary.
- Let the model classify sources or resolve permissions: rejected because security decisions cannot be delegated to an LLM.
- Accept citations returned by the model: rejected because IDs and spans can be fabricated or refer to unauthorized evidence.

## Security and privacy impact

The model cannot broaden retrieval, mint permissions, select hidden context, or establish authority. Malicious or insufficient evidence can cause a qualification or refusal. Raw evidence is minimized in traces and never logged by default.

## Evidence and verification

Use indirect prompt-injection, poisoned-source, stale/conflict, fabricated-ID, invalid-span, deleted-resource, and unauthorized-citation fixtures. Assert `INV-PROMPT-001` and `INV-CITE-001` for every answer path.

## Consequences

The product may refuse more often and requires a claim-to-evidence validation step. In exchange, citations are auditable and model fluency cannot silently become authority.
