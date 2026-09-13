# Local Platform Runbook

## Scope

P04 supplies local infrastructure, P06 adds the OpenFGA authorization model and
bootstrap operation, and P07 adds only canonical PostgreSQL metadata tables and
explicit migrations. No connectors, indexes, models, or source demo content are
created yet.
The Compose project is `permission-aware-knowledge` and all services use the
private `platform` network.

## Prerequisites

- Docker Engine or Docker Desktop with Compose v2.36 or newer.
- OpenSSL for local credential generation.
- `curl` and `jq` for the Keycloak demo-user bootstrap and private-network smoke fallback.
- At least 4 GB available memory for the platform. OpenSearch is capped at 2 GB and uses a 512 MB JVM heap.
- A host with enough disk for the named volumes and image cache.

## Start and status

```bash
make platform-config
make up
make platform-status
make openfga-bootstrap
make db-migrate
make db-schema-doc
```

`platform-config` creates `.env.local` with mode `0600` and validates the rendered Compose model. `up` waits for long-running service health checks, waits for the OpenFGA migration to complete, runs the MinIO bucket initializer, bootstraps the imported Keycloak demo users with generated local passwords, creates or updates the deterministic OpenFGA model and tuples, and applies the checked-in PostgreSQL migrations. No blind sleep is used. `platform-status` prints Compose status and runs endpoint smoke checks. `db-migrate` is safe to repeat and `db-schema-doc` regenerates the canonical schema inventory from PostgreSQL.

The smoke script first probes loopback ports. If the active Docker context does not forward published ports to the shell, it uses the pinned curl utility image on the private Compose network. This fallback is for verification only; it does not change the default host bindings.

## Service endpoints

| Service | Host endpoint | Purpose |
|---|---|---|
| PostgreSQL | `127.0.0.1:5432` | Control metadata datastore |
| OpenSearch | `https://127.0.0.1:9200` | Secured local search endpoint |
| Keycloak | `http://127.0.0.1:8080` | Local OIDC issuer and admin console |
| Keycloak management | `http://127.0.0.1:9100` | Readiness and metrics management port |
| OpenFGA | `http://127.0.0.1:8081` | Local authorization datastore API |
| MinIO API | `http://127.0.0.1:9000` | S3-compatible raw object store |
| MinIO console | `http://127.0.0.1:9001` | Local object-store console |
| Jaeger | `http://127.0.0.1:16686` | Local trace viewer |
| OTel OTLP | `127.0.0.1:4317` / `4318` | gRPC / HTTP telemetry intake |
| OTel health | `http://127.0.0.1:13133` | Collector health endpoint |
| OTel Prometheus exporter | `http://127.0.0.1:9464/metrics` | Collector metrics |
| Prometheus | `http://127.0.0.1:9090` | Local metrics store and query UI |

The Compose file binds every host port to loopback. The platform network is marked internal. OpenFGA authentication is intentionally disabled only for this loopback-bound development platform; it must not be exposed or reused as a production-like deployment setting.

## Credentials and configuration

- `.env.example` contains fake placeholders only.
- `scripts/bootstrap-platform.sh` generates random local platform credentials into `.env.local`; it never prints secret values. `scripts/bootstrap-keycloak.sh` adds generated synthetic-user passwords to the same mode-600 file and never prints them.
- `.env.local` is ignored by Git and is chmod `0600` on every invocation.
- `PLATFORM_ROTATE_OPENSEARCH_PASSWORD=1 ./scripts/bootstrap-platform.sh` rotates only the generated OpenSearch bootstrap password. Recreate the OpenSearch volume when rotating after initialization, because the initial password is consumed by the OpenSearch demo security installer.
- The current OpenSearch image uses its local demo certificate. This is acceptable only for the loopback development boundary. Production-like configuration requires operator-managed certificates, secret injection, a non-demo security configuration, and authenticated service-to-service transport.
- Keycloak uses `start-dev`; OpenFGA uses plaintext HTTP and disabled authentication. These are explicit local-development settings, not security claims.
- Keycloak imports `platform/keycloak/knowledge-local-realm.json`. The realm has a public PKCE browser client, synthetic Northstar users, group claims, and a tenant claim. It contains no password credentials. Run `make keycloak-bootstrap` after the platform is healthy to idempotently assign generated passwords.
- OpenFGA imports no model automatically from Compose. `scripts/bootstrap-openfga.sh` creates or finds the local store, creates the pinned schema 1.1 model when absent, persists non-secret store/model IDs in `.env.local`, and writes only missing tuples from `platform/openfga/seed-tuples.json`. Run `make openfga-bootstrap` after the platform is healthy to repeat the idempotent operation.
- The OpenFGA model is relationship truth, not a client-facing ACL API. The backend additionally validates the trusted resource metadata catalog, tenant membership, classification, and restricted-resource path before returning an allow.

## Persistence and reset

Named volumes are created by Compose:

| Volume | Data |
|---|---|
| `permission-aware-knowledge_postgres_data` | PostgreSQL databases and metadata |
| `permission-aware-knowledge_opensearch_data` | OpenSearch indexes and security state |
| `permission-aware-knowledge_keycloak_data` | Keycloak local runtime data |
| `permission-aware-knowledge_minio_data` | MinIO objects, including `raw` |
| `permission-aware-knowledge_prometheus_data` | Prometheus time-series data |

OpenFGA model and tuple state is stored in PostgreSQL's `openfga` database. The
store and authorization-model identifiers in `.env.local` are local operational
state, not credentials. `make reset-demo` deletes the database/volumes and the
next startup creates a fresh store/model and updates these identifiers.

The product `knowledge` database is migrated by `scripts/migrate-database.sh`.
The runner records migration filenames and SHA-256 checksums in
`schema_migrations`; it fails on checksum drift and never silently skips a
failed migration. The runtime application does not create tables.

`make down` removes containers and the private network but preserves named volumes. `make reset-demo` removes this project’s containers, network, and named volumes, then recreates the empty platform, `raw` bucket, and deterministic OpenFGA relationship state. It does not remove `.env.local`, Docker images, or files outside the project. There is no product source/demo seed yet.

## Backup and restore

P07 adds canonical metadata but does not define a complete product backup contract. Operators may make local, ignored backups of the platform volumes using Docker-native tooling. For PostgreSQL, use a password-free invocation pattern that reads the database user from the local environment without printing it:

```bash
set -a
source .env.local
set +a
mkdir -p .local-backups
docker compose --env-file .env.local exec -T postgres pg_dumpall -U "$POSTGRES_USER" > .local-backups/postgres.sql
```

Treat `.local-backups/` as sensitive local data and never commit it. MinIO objects require an S3-aware copy or volume backup; OpenSearch, Keycloak, and Prometheus volumes are operational state and must be backed up only when their version-specific restore procedure is known. A restore must be followed by `make platform-status` and service-specific integrity checks. Reset is destructive and is not a backup.

## Container posture

The checked image configuration runs OpenSearch and Keycloak as UID 1000, OpenFGA as UID 65532, Jaeger and OTel as UID 10001, and Prometheus as `nobody`. PostgreSQL's official entrypoint starts the database process as its bundled `postgres` user. MinIO's pinned official image starts as root in this local configuration because its entrypoint and named-volume permissions require it; this is a tracked hardening gap for a future platform-hardening phase, not a claim of universal non-root coverage.

All Compose services have explicit healthchecks. Distroless images use native executable validation where no shell or HTTP client exists. Container image tags are pinned; MinIO server/client and the smoke utility are additionally pinned to verified architecture-specific digests. Full image vulnerability scanning remains gated on local Trivy availability.

## Failure triage

- `make up` fails during image pull: verify the configured registry is reachable and that the pinned image manifest supports the host architecture.
- OpenSearch restarts with a password validation error: rotate the local bootstrap password, then run `make reset-demo` if the volume has already been initialized.
- A one-shot migration or initializer exits non-zero: inspect `docker compose logs openfga-migrate minio-init`, then inspect the migration runner output; do not manually mark the platform ready.
- Host loopback probes fail while container health is green: inspect `docker context show`; the smoke script's private-network fallback is expected for remote or VM-backed Docker contexts.
- Missing ShellCheck or Trivy blocks `make verify-release`: install the tools locally and rerun the release gate; do not weaken or skip the target.
