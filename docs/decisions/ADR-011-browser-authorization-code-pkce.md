# ADR-011: Browser Authorization Code with PKCE

- Status: accepted
- Phase: P05
- Date: 2026-09-13

## Context

The local React client needs to authenticate against Keycloak without exposing
client secrets or persisting bearer tokens in browser storage. The API must
independently validate the resulting access token and keep authentication
separate from later OpenFGA authorization.

## Decision

Use the OpenID Connect Authorization Code flow with a public Keycloak client and
S256 PKCE. Store only transient state and the code verifier in `sessionStorage`;
store access tokens in a module-memory token store, expire them locally, and
clear them during logout. The backend validates the signed access token with a
strict issuer, audience, algorithm, required-claim, time, and key policy.

The local API exposes `/api/v1/auth/me` and `/api/v1/auth/logout`. Logout
revokes the validated session handle in the current process and clears the
browser token. A future multi-process/BFF deployment must use a durable
revocation/session store and preserve the same generic error and fail-closed
behavior.

## Alternatives considered

- **Implicit flow:** rejected because it exposes tokens through the browser
  front-channel and has weaker modern security properties.
- **Resource Owner Password Credentials:** rejected because the browser would
  handle user passwords and it bypasses the authorization-code protections.
- **Long-lived HttpOnly cookie BFF:** deferred; it can improve token isolation,
  but needs a durable session store, CSRF defenses, proxy deployment, and
  multi-process invalidation design that is outside this phase.
- **Frontend-only JWT validation:** rejected because client validation is not an
  API trust boundary and cannot enforce server authorization.

## Consequences

PKCE protects the authorization-code exchange without a browser secret, and
memory-only access tokens reduce persistence exposure. Full-page logout and
refresh behavior must be implemented carefully in later UI work. The in-process
revocation registry is intentionally local-only and is a documented scaling
boundary, not a claim of distributed session invalidation.

## Verification

Unit tests cover S256 authorization parameters, memory-only token expiry and
clearing, and backend validation/revocation. Browser integration and live
Keycloak login remain a later end-to-end phase.
