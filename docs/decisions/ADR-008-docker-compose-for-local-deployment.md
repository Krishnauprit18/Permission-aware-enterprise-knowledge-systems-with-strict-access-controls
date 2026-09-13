# ADR-008: Docker Compose for Local Deployment

- Status: `accepted`
- Date: 2026-09-13
- Owners: architecture and operations engineering
- Related phase: P02

## Context

The complete application requires an API, frontend, worker, PostgreSQL,
OpenSearch, OpenFGA, Keycloak, MinIO, local model services, and observability.
The product is local/on-prem style and does not require Kubernetes or cloud
infrastructure.

## Decision

Use Docker Compose as the reference deployment and infrastructure definition.
Compose files define service versions, private networks, health/readiness checks,
volumes, runtime secret injection, resource limits where supported, startup
dependencies, and operator-facing ports. Development overrides must remain
clearly separate from secure defaults.

## Alternatives considered

- Kubernetes: rejected for this scope because it adds cluster, packaging,
  policy, and operations complexity without a current product requirement.
- Cloud-managed services: rejected because local operation without cloud
  dependency is a core requirement.
- Manually installed host services: rejected as the reference because versions,
  networking, reset behavior, and reproducibility would vary across machines.

## Security and privacy impact

Infrastructure services use private networks and least-privilege credentials.
No default credentials or secrets are committed. Persistent volumes, backups,
ports, parser/model isolation, and reset behavior require explicit review.

## Evidence and verification

Later checks must validate pinned images, health/readiness, private service
reachability, secret injection, durable volumes, clean startup/shutdown,
reset/seed behavior, backup/restore, and no unintended host ports.

## Consequences

The system has one reproducible local topology and no Kubernetes manifests.
Compose is not treated as a claim about production scale; future deployment
modes require a separate phase and threat-model update.
