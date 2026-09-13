# Architecture Decision Records

Material decisions are recorded as numbered ADRs. Historical chat is not an authority for project behavior.

- `ADR_TEMPLATE.md` is the required starting point for a new decision.
- P01 accepted decisions: authorization before model context, separate view/share policy, untrusted retrieved content with validated citations, and fail-closed non-disclosing refusals.
- P02 accepted decisions: OpenSearch hybrid retrieval, OpenFGA relationship authorization, Keycloak local OIDC, Docker Compose local deployment, local model adapter interfaces, and the Python/FastAPI/React/PostgreSQL/MinIO/worker/OpenTelemetry stack with Redis deferred.
- P05 accepted decision: browser Authorization Code + S256 PKCE with memory-only access tokens and independently validated backend identities in `ADR-011-browser-authorization-code-pkce.md`.
- P06 accepted decision: OpenFGA schema 1.1 relationship model with application-side tenant/classification enforcement, explicit restricted access, separate external sharing, and versioned decision fingerprints in `ADR-012-openfga-authorization-model-v1.md`.
