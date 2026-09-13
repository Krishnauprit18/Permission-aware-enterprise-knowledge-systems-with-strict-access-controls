# Authentication Model

## Boundary

Keycloak is the local OpenID Connect issuer for the synthetic
`knowledge-local` realm. The browser uses the public
`knowledge-web-local` client with Authorization Code + PKCE using the S256
code challenge method. The browser stores the short-lived PKCE state and
verifier only in `sessionStorage`; access tokens are held in a module-memory
store and are cleared on expiry or logout. Tokens are never written to
`localStorage`, cookies, URLs, logs, traces, or application state sent to the
backend.

The API does not trust frontend route guards, tenant selectors, group inputs, or
client-supplied ACL filters. It validates the signed access token and constructs
a `PrincipalContext` containing subject ID, tenant claim, groups, selected safe
claims, and the server correlation ID. This identity is an input to later
authorization; it does not itself grant access to resources or evidence.

## Token validation policy

`OIDCValidatorConfig` requires an absolute issuer, a non-empty audience, the
explicit `RS256` algorithm, and a clock-skew allowance between zero and 300
seconds. Local HTTP is accepted only for loopback issuers. The validator
requires `iss`, `aud`, `sub`, `iat`, `nbf`, and `exp`, verifies the Keycloak
signing key selected by `kid`, checks issuer/audience/signature/expiry/not-before,
and rejects an issued-at timestamp too far in the future. The JWKS endpoint is
derived from the configured Keycloak issuer; callers cannot provide an arbitrary
JWKS URL.

The current local session boundary also requires a `sid` or `jti` handle and
keeps an in-process revocation registry until token expiry. Logout validates the
current token, revokes that handle, clears browser memory, and deletes the
secure/HttpOnly/SameSite cookie name reserved for a future BFF session. The
current browser flow does not use an authentication cookie. A multi-process
deployment must replace the in-memory store with a durable, tenant-safe session
store before scaling the API.

An `enabled: false` claim is rejected when present, which gives the validator a
deterministic disabled-principal fail-closed path. Keycloak user disablement and
administrative session revocation must be paired with short access-token
lifetimes and provider-side session invalidation; a later phase must add a
durable back-channel/status check if immediate disablement across already-issued
tokens is required.

## HTTP behavior

- Missing, malformed, expired, disabled, tampered, wrong-issuer, wrong-audience,
  and unavailable-provider credentials all produce the generic `401
  authentication required` response.
- Detailed reasons are restricted to an allowlisted structured event containing
  outcome, reason code, correlation ID, and optional duration. Authorization
  headers, cookies, bearer values, password values, and raw claims are never
  logged.
- Every response receives a fresh `X-Correlation-ID`; a client-provided value is
  not reused as the server identifier.
- State-changing cookie-authenticated endpoints must use CSRF protection. P05's
  browser API uses an Authorization header and no session cookie, so CSRF is not
  the bearer transport control. Any future cookie/BFF endpoint must add an
  origin/CSRF-token check before it is enabled.
- Auth-sensitive routes are to be rate-limited by source address and principal
  where available, with bounded request size and concurrency. The local P05
  process documents this strategy but does not add a Redis dependency or pretend
  that an in-memory counter is suitable for a multi-process deployment.

## Demo identity data

`platform/keycloak/knowledge-local-realm.json` is deterministic and contains
only synthetic Northstar users, groups, client metadata, and tenant attributes.
It contains no password credentials. `scripts/bootstrap-keycloak.sh` assigns
generated passwords to the imported users and stores them only in the ignored,
mode-600 `.env.local` file. The script is idempotent and never prints generated
passwords or admin tokens.

## Verification references

P05 tests cover successful validation, missing/expired/wrong-issuer/wrong-
audience/tampered/disabled tokens, group parsing, generic failures, log
redaction, in-process logout invalidation, PKCE request construction, token
expiry, and explicit memory clearing. These are project verification mappings,
not certification claims:

- OWASP ASVS 5.0.0: V2 authentication, V3 session management, V7 error/logging
  behavior, and V8 data protection.
- NIST SSDF 1.1: prepare the organization, protect software, produce
  well-secured software, and respond to vulnerabilities through reviewed
  authentication changes and regression evidence.
- OWASP Top 10:2025: broken access control, authentication failures, injection,
  security misconfiguration, and software supply-chain failures.
- OWASP GenAI/LLM Top 10 2026: identity/authentication remains outside model
  control, and no model output can authenticate or authorize a principal.
