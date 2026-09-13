# Architecture

System boundaries, typed contracts, data flow, storage, source adapters, retrieval, answer generation, and trace design will be documented here as those phases are executed.

- `TRUST_MODEL.md` defines actors, assets, trust boundaries, and contract-level data flows without selecting technologies.
- `REFERENCE_ARCHITECTURE.md` defines the selected P02 local-first stack, component ownership, deployment boundaries, and failure posture.
- `PIPELINES.md` defines the mandatory ingestion, query, deletion/change, and role-change ordering contracts.
- `AUTHORIZATION_ARCHITECTURE.md` defines OpenFGA-backed current authorization and the metadata-first candidate/fine-check boundary.
- `PORTS_AND_DEPENDENCY_RULES.md` defines typed ports, security-bearing types, layering, and import rules.
- `VERSIONING.md` defines API, index, embedding, prompt, evaluation, authorization, schema, and release compatibility versions.
- `DATA_MODEL.md` defines canonical PostgreSQL entities, lifecycle, stable IDs, and authority boundaries.
- `ARCHITECTURE_REVIEW.md` records the P02 invariant, pipeline, dependency, deployment, and residual-risk review.
- `PERMISSION_FIRST_RETRIEVAL.md` defines the P12 authorization-first query ordering, immutable filter construction, hybrid candidate paths, and ListObjects scale boundary.
