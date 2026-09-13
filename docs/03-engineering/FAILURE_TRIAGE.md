# Failure Triage

Start with the narrow target that failed, then rerun `make verify` after the fix. Do not bypass a required gate by changing its threshold or suppressing output.

| Symptom | First action | Common cause |
| --- | --- | --- |
| `uv` cannot resolve or install | Run `uv lock --directory backend` and inspect Python/dependency constraints. | Unsupported Python version, registry access, or changed `pyproject.toml`. |
| Ruff or Prettier reports changes | Run the formatter locally, inspect the diff, then rerun the check. | Unformatted source or generated output not excluded. |
| mypy or TypeScript fails | Fix the type at its boundary; do not add `Any` or `# type: ignore` without a documented exception. | Missing annotation, optional value, or an invalid dependency import. |
| Unit coverage falls below threshold | Add behavior-focused tests for the changed source. | New executable code lacks tests or coverage scope is incorrect. |
| Architecture test fails | Inspect imports and move framework/infrastructure code outward. | Domain/application layer depends on an adapter or web framework. |
| Bandit or Semgrep reports a finding | Validate against source and runtime reachability, then remediate or record a justified false positive. | Unsafe API, dynamic execution, secret-like value, or scanner heuristic. |
| `npm audit` or `pip-audit` reports a vulnerability | Determine affected path, fixed version, and compatibility impact before upgrading. | Transitive dependency advisory or stale lockfile. |
| Secret scan reports a value | Remove it from tracked files and logs, rotate it if real, then regenerate the baseline only for reviewed false positives. | Credential-like fixture, token, or generated report. |
| Docker lint cannot run | Check Hadolint or Docker BuildKit availability and record the missing tool. | Local scanner is not installed or Docker lacks `build --check`. |
| Container scan cannot run | Install or provide Trivy, then run `make container-scan`. | Trivy is not installed or a Dockerfile configuration finding is present. |
| Compose host probes fail while healthchecks pass | Run `docker context show` and inspect `docker compose ps`; the smoke script can probe the private network for VM-backed contexts. | The Docker daemon may not forward published ports to the current shell. |
| OpenSearch restarts on startup | Rotate the local bootstrap password and reset the local volume if already initialized. | OpenSearch demo security requires uppercase, lowercase, digit, and special-character password classes. |
| One-shot platform initializer fails | Inspect `docker compose logs openfga-migrate minio-init`; rerun `make up` after remediation. | A migration or bucket setup failed and readiness must not be inferred. |
| Release gate lacks a scanner | Keep the result `BLOCKED` for release evidence. | Release-only tool is absent; never silently treat it as passed. |

Security findings are fixed with a regression test in the same phase whenever practical. A failure on an authorization, secret, or context-construction path is a phase blocker until reviewed and resolved.
