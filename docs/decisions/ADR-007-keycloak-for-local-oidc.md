# ADR-007: Keycloak for Local OIDC

- Status: `accepted`
- Date: 2026-09-13
- Owners: architecture and security engineering
- Related phase: P02

## Context

The product requires authenticated enterprise users, local operation, standards-
based browser/API sessions, administrative identity management, and a clean
separation between authentication and resource authorization.

## Decision

Use Keycloak as the local OpenID Connect identity provider. FastAPI validates
OIDC tokens and constructs a server-owned principal bound to one tenant. Keycloak
identity and group claims may seed trusted identity mappings, but OpenFGA and
application policy decide resource access and externalability.

## Alternatives considered

- Build authentication in the application: rejected because credential,
  session, token, recovery, and administrative flows are security-critical and
  should use a maintained identity provider.
- Hosted identity provider: rejected for the default because the product must run
  locally without a cloud dependency.
- Reverse-proxy-only authentication: rejected because the application still
  needs verifiable identity/session semantics and explicit token validation.

## Security and privacy impact

Realm/client configuration, signing keys, redirect URIs, token audience/issuer,
session lifetime, administrative access, and secret injection require secure
defaults and test evidence. Authentication success never implies resource
authorization. Invalid or unavailable token validation rejects the request.

## Evidence and verification

Test valid, expired, malformed, replayed where applicable, wrong-audience,
wrong-issuer, wrong-tenant, and privilege-change cases. Review exported realm
configuration for secrets and insecure development defaults.

## Consequences

Keycloak adds a local stateful service and configuration lifecycle, but avoids
custom authentication and supports realistic enterprise OIDC behavior.
