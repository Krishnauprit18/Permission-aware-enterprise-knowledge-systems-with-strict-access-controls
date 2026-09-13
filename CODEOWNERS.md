# CODEOWNERS Guidance

This repository is currently maintained by one owner. Before a second maintainer is added, replace this document with a root-level `.github/CODEOWNERS` file and require review for:

- `backend/src/knowledge_system/domain/`, `application/`, and `bootstrap/`;
- `docs/02-security/`, `docs/decisions/`, and authorization-related tests;
- `Makefile`, dependency manifests, lockfiles, Dockerfiles, and security tooling.

Security-sensitive changes require an explicit regression test and a recorded review, even in a solo workflow.
