# Confidentiality Policy And Customer-Safe Mode

## Boundary

P15 sits after P13's current `can_view` reauthorization and before P14's
context builder:

```text
P13 authorized EvidenceResolution
  -> trusted answer mode policy
  -> INTERNAL: same authorized packets + safe classification warnings
  -> CUSTOMER_SAFE: metadata allowlist + current can_share_externally checks
  -> filtered EvidenceResolution
  -> P14 bounded context builder
  -> local model
```

The policy service accepts no raw client ACL filters, model output, source text
instructions, or client-supplied classification. It returns a new immutable
resolution for customer-safe mode. P14 receives that filtered resolution, so
internal-only text is absent before model context construction.

## Precedence

1. Current tenant and `can_view` authorization must already have succeeded in
   P12/P13. P15 never grants view access.
2. Deleted, missing, malformed, or stale authorization-bound evidence is not
   eligible for a model context.
3. Internal mode may use any authorized classification, but returns fixed
   classification warnings and never labels the content customer-safe.
4. Customer-safe mode requires all of:
   - `classification` is `PUBLIC` or `CUSTOMER_SHAREABLE`;
   - `external_shareable` is explicitly `true`;
   - current OpenFGA `can_share_externally` is `ALLOW`.
5. Missing classification or shareability metadata is denied conservatively.
   A share relationship cannot override non-shareable classification or missing
   metadata. An LLM cannot change any of these decisions.
6. A customer-safe conflict is retained only when every member of the conflict
   survives policy selection. The model never sees a partial conflict group.

The OpenFGA share relation remains independent from `can_view`. An internal
viewer with no share relation cannot produce a customer-safe answer. A share
reviewer also cannot override `INTERNAL`, `CONFIDENTIAL`, or `RESTRICTED`
classification.

## Response policy contract

P14 `GroundedAnswer` includes `answer_mode`, `policy_status`, and fixed
`policy_warnings` with stable codes. Warnings contain no evidence IDs, titles,
counts, or source text. Customer-safe refusal uses generic insufficient-evidence
language even when the underlying reason is a denied, missing, or restricted
source. Inaccessible Legal-only content is absent from the P13 resolution and
therefore cannot be named by P15.

The current warning taxonomy is:

| Code | Meaning | User-safe behavior |
|---|---|---|
| `INTERNAL_CONTENT_PRESENT` | Authorized internal evidence is used | Warn not to share externally |
| `CONFIDENTIAL_CONTENT_PRESENT` | Authorized confidential evidence is used | Strong warning not to share externally |
| `RESTRICTED_CONTENT_PRESENT` | Authorized restricted evidence is used | High-severity warning not to share externally |
| `CUSTOMER_SAFE_POLICY_APPLIED` | A safe subset was selected | Generic informational notice |
| `CUSTOMER_SAFE_INSUFFICIENT_EVIDENCE` | No safe evidence remains | Generic refusal |
| `POLICY_UNAVAILABLE` | Current share policy could not be checked | Generic unavailable response |

`ALLOW`, `ALLOW_WITH_WARNINGS`, `FILTERED`, `REFUSED`, and `UNAVAILABLE` are
machine-readable policy statuses. Excluded-resource details remain internal
operator/evaluation data and are not part of the user response.

## Evaluation hook

Policy evaluation is separate from generation evaluation. A test or future
evaluation runner compares the selected evidence IDs and policy status against
the permission/shareability fixture, then independently evaluates grounded
claims and citations. The model input assertion must prove that every
customer-safe context evidence ID is in the policy-filtered resolution and that
no excluded text occurs in the serialized context. Policy checks must be rerun
for every answer request so a classification change takes effect on the next
answer without re-embedding.
