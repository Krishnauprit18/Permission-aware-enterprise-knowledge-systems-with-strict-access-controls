# ADR-017: Deterministic Confidentiality Policy Before Generation

## Status

Accepted in P15.

## Context

An authenticated user may view internal evidence that must not be used in an
answer intended for a customer. Asking a model to redact internal text after it
has entered model context is too late and makes shareability dependent on model
behavior.

## Decision

Keep `can_view` and `can_share_externally` as separate policy decisions. Add a
trusted application policy boundary between P13 evidence resolution and P14
generation. Internal mode passes current authorized packets and emits fixed
classification warnings. Customer-safe mode selects a new packet subset only
when trusted metadata is explicitly `PUBLIC` or `CUSTOMER_SHAREABLE`, the
shareability flag is true, and the current OpenFGA share relation allows it.
The filtered result, not the original resolution, is passed to P14.

Missing policy metadata, denied share authorization, or authorization service
failure never widens scope; they conservatively filter or fail closed with
generic user-facing text. Warning codes and policy statuses are typed and do not
contain protected identifiers or counts.

## Alternatives considered

- Ask the LLM to redact internal evidence: rejected because unauthorized or
  non-shareable text would already have entered model context.
- Infer shareability from `can_view`: rejected because internal viewing and
  external sharing are different business permissions.
- Let an LLM classify content: rejected because security and confidentiality
  decisions must be deterministic and auditable.
- Add a second retrieval backend: rejected for P15; reusing P13 packets keeps
  the policy boundary small while ensuring selection occurs before P14 context.

## Consequences

Customer-safe mode can return less evidence or refuse even when internal mode
answers. Classification changes are observed on the next request because the
policy is evaluated per request and has no result cache. Policy status/warnings
are now part of the answer contract and require independent evaluation evidence.
