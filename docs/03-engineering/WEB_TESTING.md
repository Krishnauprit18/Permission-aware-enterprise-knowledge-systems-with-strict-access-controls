# Web Testing

## Commands

| Command | Runtime | Purpose |
|---|---|---|
| `npm --prefix frontend run test` | fast | React, API-client, OIDC, and coverage gates |
| `npm --prefix frontend run typecheck` | fast | Strict TypeScript validation |
| `npm --prefix frontend run lint` | fast | ESLint validation |
| `npm --prefix frontend run test:e2e` | slow | Chromium login/query/citation contract flow |

The Playwright flow uses route-controlled local Keycloak and API responses. It
tests the browser boundary, PKCE callback behavior, memory-only token use,
mode-bound query submission, citation display, provenance display, and request
ID rendering without requiring a live model or cloud service. It does not
claim live authorization or generation coverage; those are backend integration
tests and future local composition evidence.

## Failure triage

1. Run the focused failing command from `frontend/` and inspect the first
   assertion, not generated trace contents as application data.
2. For `test:e2e`, ensure the pinned Playwright package and its Chromium binary
   are installed locally; the test starts Vite on loopback port 4173.
3. For API failures, run `uv run --directory backend pytest
   tests/integration/test_product_api.py -q --no-cov` and inspect only safe
   status/request IDs.
4. Never weaken auth, policy, CSP, citation, or escaping checks to make a test
   green. Add a regression test for every security fix.
