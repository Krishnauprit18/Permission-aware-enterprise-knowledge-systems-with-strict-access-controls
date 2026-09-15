.DEFAULT_GOAL := verify
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

BACKEND_RUN := uv run --directory backend
FRONTEND_RUN := npm --prefix frontend run
REPORTS_DIR := $(CURDIR)/reports
PLATFORM_SERVICES := postgres opensearch keycloak openfga minio jaeger otel-collector prometheus
SHELLCHECK_IMAGE := koalaman/shellcheck:stable@sha256:b9389b73c8f26f710a7171cb7d8848a34a9c1e07a7865e727c9ec4ce99f9a83f
TRIVY_IMAGE := aquasec/trivy:0.56.2@sha256:9aebdee5e85129a1bdd9977676baa6cf0579195fc4809570cc9dd55f6e92863c
SEMGREP_SCAN := SEMGREP_SETTINGS_FILE="$${TMPDIR:-/tmp}/knowledge-system-semgrep-settings.yml" SEMGREP_LOG_FILE="$${TMPDIR:-/tmp}/knowledge-system-semgrep.log" SEMGREP_VERSION_CACHE_PATH="$${TMPDIR:-/tmp}/knowledge-system-semgrep-version" SEMGREP_SEND_METRICS=off semgrep --disable-version-check --config security/semgrep.yml

.PHONY: bootstrap fmt lint lint-docs prompt-integrity dataset-validate eval typecheck test test-unit test-integration \
 test-security sbom scan container-lint container-scan architecture-test verify verify-release reindex-demo \
 shellcheck platform-config platform-status keycloak-bootstrap openfga-bootstrap db-migrate db-schema-doc up down reset-demo seed-demo

bootstrap:
	command -v uv >/dev/null
	command -v npm >/dev/null
	uv python install 3.12
	uv sync --directory backend --all-groups
	npm --prefix frontend ci

fmt:
	$(BACKEND_RUN) ruff format --check src tests
	$(FRONTEND_RUN) fmt:check

lint:
	$(BACKEND_RUN) ruff check src tests
	$(FRONTEND_RUN) lint

lint-docs:
	npm --prefix frontend exec -- markdownlint-cli2 AGENTS.md 'docs/**/*.md'

prompt-integrity:
	./scripts/verify-prompt-integrity.sh

dataset-validate:
	$(BACKEND_RUN) python -m knowledge_system.dataset.validator

eval:
	if [[ -f "$(REPORTS_DIR)/evals/1.1.0/summary.json" ]]; then \
		$(BACKEND_RUN) python -m knowledge_system.evaluation --output-dir "$(REPORTS_DIR)/evals/1.1.0" --previous-report "$(REPORTS_DIR)/evals/1.1.0/summary.json"; \
	else \
		$(BACKEND_RUN) python -m knowledge_system.evaluation --output-dir "$(REPORTS_DIR)/evals/1.1.0"; \
	fi

typecheck:
	$(BACKEND_RUN) mypy
	$(FRONTEND_RUN) typecheck

test: test-unit test-integration

test-unit:
	$(BACKEND_RUN) pytest -m unit --cov=knowledge_system.domain
	$(FRONTEND_RUN) test:unit

test-integration:
	$(BACKEND_RUN) pytest -m integration --no-cov

test-security:
	$(BACKEND_RUN) bandit --quiet --recursive src
	$(SEMGREP_SCAN) --error --quiet backend/src
	$(BACKEND_RUN) pytest -m security --no-cov

architecture-test:
	$(BACKEND_RUN) pytest -m integration --no-cov

shellcheck:
	if command -v shellcheck >/dev/null; then \
		shellcheck scripts/*.sh; \
	else \
		docker run --rm -v "$(CURDIR):/mnt:ro" $(SHELLCHECK_IMAGE) \
			/mnt/scripts/bootstrap-platform.sh /mnt/scripts/bootstrap-keycloak.sh /mnt/scripts/bootstrap-openfga.sh \
			/mnt/scripts/migrate-database.sh /mnt/scripts/generate-db-schema-doc.sh \
			/mnt/scripts/compose-local.sh \
			/mnt/scripts/platform-smoke.sh /mnt/scripts/verify-local.sh \
			/mnt/scripts/verify-release.sh; \
	fi

sbom:
	mkdir -p "$(REPORTS_DIR)"
	uv export --directory backend --no-emit-project --format requirements.txt --output-file "$(REPORTS_DIR)/backend-requirements.txt"
	$(BACKEND_RUN) cyclonedx-py requirements "$(REPORTS_DIR)/backend-requirements.txt" --output-format json --outfile "$(REPORTS_DIR)/backend-sbom.json"
	npm --prefix frontend sbom --sbom-format cyclonedx > "$(REPORTS_DIR)/frontend-sbom.json"

scan:
	mkdir -p "$(REPORTS_DIR)"
	uv export --directory backend --no-dev --no-emit-project --format requirements.txt --output-file "$(REPORTS_DIR)/backend-requirements.txt"
	$(BACKEND_RUN) pip-audit -r "$(REPORTS_DIR)/backend-requirements.txt"
	npm --prefix frontend audit --omit=dev --audit-level=high
	$(BACKEND_RUN) detect-secrets scan --all-files --baseline "$(CURDIR)/.secrets.baseline" --exclude-files '(^|/)(\.git|\.venv|node_modules|coverage|dist|build|reports|\.mypy_cache|\.pytest_cache|\.ruff_cache)(/|$$)' "$(CURDIR)"
	$(SEMGREP_SCAN) --error backend/src

container-lint:
	./scripts/bootstrap-platform.sh
	./scripts/compose-local.sh config --quiet
	if command -v hadolint >/dev/null; then \
		hadolint backend/Dockerfile frontend/Dockerfile; \
	else \
		docker build --check -f backend/Dockerfile backend; \
		docker build --check -f frontend/Dockerfile frontend; \
	fi

container-scan:
	if command -v trivy >/dev/null; then \
		trivy config --skip-check-update --severity HIGH,CRITICAL compose.yml; \
		trivy config --skip-check-update --severity HIGH,CRITICAL backend/Dockerfile; \
		trivy config --skip-check-update --severity HIGH,CRITICAL frontend/Dockerfile; \
	else \
		docker run --rm -v "$(CURDIR):/work:ro" $(TRIVY_IMAGE) \
			config --skip-check-update --severity HIGH,CRITICAL /work/compose.yml; \
		docker run --rm -v "$(CURDIR):/work:ro" $(TRIVY_IMAGE) \
			config --skip-check-update --severity HIGH,CRITICAL /work/backend/Dockerfile; \
		docker run --rm -v "$(CURDIR):/work:ro" $(TRIVY_IMAGE) \
			config --skip-check-update --severity HIGH,CRITICAL /work/frontend/Dockerfile; \
	fi

platform-config:
	./scripts/bootstrap-platform.sh
	./scripts/compose-local.sh config --quiet

verify: fmt lint lint-docs prompt-integrity dataset-validate eval typecheck test test-security architecture-test
	@printf '%s\n' 'Local fast verification passed.'

verify-release: verify shellcheck scan sbom container-lint container-scan
	@printf '%s\n' 'Local release verification passed.'

up:
	./scripts/bootstrap-platform.sh
	./scripts/compose-local.sh up -d --remove-orphans --wait --wait-timeout 120 $(PLATFORM_SERVICES)
	./scripts/compose-local.sh run --rm --no-deps minio-init
	./scripts/bootstrap-keycloak.sh
	./scripts/bootstrap-openfga.sh
	./scripts/migrate-database.sh

keycloak-bootstrap:
	./scripts/bootstrap-keycloak.sh

openfga-bootstrap:
	./scripts/bootstrap-openfga.sh

db-migrate:
	./scripts/migrate-database.sh

db-schema-doc:
	./scripts/generate-db-schema-doc.sh

platform-status:
	./scripts/bootstrap-platform.sh
	./scripts/compose-local.sh ps
	./scripts/platform-smoke.sh

down:
	if [[ -f .env.local ]]; then ./scripts/compose-local.sh down --remove-orphans; else printf '%s\n' 'Platform is not initialized.'; fi

reset-demo:
	./scripts/bootstrap-platform.sh
	./scripts/compose-local.sh down --volumes --remove-orphans
	./scripts/compose-local.sh up -d --remove-orphans --wait --wait-timeout 120 $(PLATFORM_SERVICES)
	./scripts/compose-local.sh run --rm --no-deps minio-init
	./scripts/bootstrap-keycloak.sh
	./scripts/bootstrap-openfga.sh
	./scripts/migrate-database.sh

seed-demo:
	$(MAKE) dataset-validate
	@printf '%s\n' 'Synthetic demo/evaluation fixtures validated; runtime ingestion job bootstrap remains future phase work.'

reindex-demo:
	./scripts/reindex-demo.sh
