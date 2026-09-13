# ADR-004: Protected Failures Refuse Without Existence Disclosure

- Status: `accepted`
- Date: 2026-09-13
- Owners: product and security engineering
- Related phase: P01

## Context

Missing identity, unavailable policy state, revoked access, deletion lag, conflicting evidence, or insufficiently authoritative evidence can make an answer unsafe. Detailed errors may reveal that a protected resource exists.

## Decision

Protected authorization and policy failures fail closed. User-facing refusal or insufficient-evidence responses are generic by default and do not confirm resource existence, classification, owner, counts, or contents. Authorized audit traces retain a reason code, stable IDs where safe, policy version, and operational outcome without raw protected content.

## Alternatives considered

- Return detailed "permission denied" resource errors: rejected because they create an existence oracle.
- Continue with stale or partial policy state: rejected because uncertainty on protected paths must not grant access.
- Guess through conflicts or missing evidence: rejected because unsupported confidence is worse than a bounded refusal.

## Security and privacy impact

The product may appear less helpful for ambiguous or degraded requests and may require operator-visible diagnostics. This reduces timing, wording, and error-channel disclosure and preserves fail-closed behavior.

## Evidence and verification

Probe inaccessible, deleted, nonexistent, stale, conflict, and policy-unavailable cases. Assert generic user responses, no protected identifiers or counts, bounded observable differences, and complete authorized reason-code traces.

## Consequences

Support and operations need trace access to diagnose refusals. The user experience must explain lack of accessible evidence without explaining hidden resource state.
