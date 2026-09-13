# Prompt Ledger

Store each sanitized phase prompt once under `docs/codex/prompts/PXX.md`. Record only a short summary, SHA-256 hash, outcome, and checkpoint commit here.

| Phase | Summary | SHA-256 | Outcome | Checkpoint commit |
|---|---|---|---|---|
| P00 | Bootstrap the engineering constitution and durable project operating system; no product features. | `de5e693fef378848621ace61a2866c558171292005d6e46b428fa9966dff9614` | PASS | `fd13c0f` |
| P01 | Define the product specification, trust model, threat model, standards verification plan, and settled security ADRs without implementation. | `59fd9062dd9208cf5ab54f29cf39342671419c47fa19ac51e30540108219fed5` | PASS | `5570e59` |
| P02 | Define the local-first architecture, secure pipelines, dynamic authorization, typed ports, versioning, dependency rules, and technology ADRs without business implementation. | `0914bd201ec8ac58df9f3d701be075d890b48b08f93ac8c90a29d9b21a7d0315` | PASS | `f512236` |
| P03 | Build the typed repository scaffold, lockfiles, automated quality/security gates, boundary tests, and local verification documentation without product features. | `70e9de5408893bdc3a546957df2c752f2cb121372952b8acd5522d7ae992dc77` | PASS | `cc91683` |
| P04 | Build the private local Docker Compose platform, readiness/bootstrap/reset/status operations, smoke tests, observability path, and operations documentation without product features. | `da0aa3ea441b622c9ebfaed1cf124242caaf035d0b99ef9596309c43fa30e0e6` | PASS | `35801fc` |
| P05 | Implement local Keycloak/OIDC identity and authentication with PKCE, strict token validation, generic/redacted auth handling, logout/revocation, deterministic demo bootstrap, and auth regression tests. | `d13c837c50cfa9208fd70d0625ef322599109ef94f0375849e288b966fa4b69e` | PASS | `03be6c1` |
| P06 | Implement first-class OpenFGA authorization with typed checks/scopes, tenant/account/department/restricted/share relationships, deterministic model/tuple bootstrap, versioned audit fingerprints, and failure-closed tests without retrieval. | `e12e022bda91e2e8e6f1b070164795fbace7a91df69f209bfa9d53894e986fae` | PASS | `acb3083` |
