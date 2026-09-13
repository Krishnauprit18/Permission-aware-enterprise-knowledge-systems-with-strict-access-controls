# Permission-Aware Enterprise Knowledge System

This repository is a local-first scaffold for a permission-aware enterprise knowledge system. P03 establishes typed backend and frontend boundaries plus automated developer gates; product workflows are intentionally deferred to later numbered phases.

## Quick start

```bash
cp .env.example .env
make bootstrap
make verify
```

The `.env.example` values are synthetic local placeholders. Never put real credentials in source, fixtures, prompts, or logs.

## Local platform

P04 provides the local infrastructure boundary through Docker Compose. Generate ignored credentials and start the platform with:

```bash
make platform-config
make up
make platform-status
```

The service ports are loopback-only by default. See [the local platform runbook](docs/05-operations/LOCAL_PLATFORM.md) for endpoints, persistent data, reset semantics, and the production-like hardening differences.

## Developer checks

```bash
make verify          # fast deterministic gate
make verify-release  # slower security, SBOM, dependency, and container checks
```

See [the quality gates](docs/03-engineering/QUALITY_GATES.md), [the toolchain](docs/03-engineering/TOOLCHAIN.md), and [failure triage](docs/03-engineering/FAILURE_TRIAGE.md) for runtime expectations and remediation guidance.

## Scope guard

No authentication, authorization service, connector, retrieval, model, persistence, or deployment implementation is present yet. The future product must preserve the repository invariants in [AGENTS.md](AGENTS.md), especially authorization before LLM context construction and separate `can_view` and `can_share_externally` decisions.

## License

Released under the MIT License. Standards references in project documentation describe alignment and verification guidance only; they are not certification claims.
