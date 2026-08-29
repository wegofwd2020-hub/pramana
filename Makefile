# Pramana developer Makefile.
# Run `make help` for available targets.

.PHONY: help install dev-install lint format type-check test test-cov \
        pre-commit clean migrate migrate-create run security-scan status grant-role archive-audit

PYTHON := python3
PIP := $(PYTHON) -m pip

# Overridable so a busy port does not make the target unusable:
#   make run PORT=8137
HOST ?= 0.0.0.0
PORT ?= 8000

help:  ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install runtime dependencies only.
	$(PIP) install -e .

dev-install:  ## Install runtime + dev dependencies and pre-commit hooks.
	$(PIP) install -e ".[dev]"
	pre-commit install

lint:  ## Run ruff linter (no autofix).
	ruff check pramana tests

format:  ## Auto-format and auto-fix lints with ruff.
	ruff check --fix pramana tests
	ruff format pramana tests

type-check:  ## Run mypy.
	mypy pramana

test:  ## Run the full test suite.
	pytest

test-cov:  ## Run tests with coverage report.
	pytest --cov=pramana --cov-report=term-missing --cov-report=html

test-fast:  ## Run only fast unit tests (skip slow & integration).
	pytest -m "not slow and not integration"

pre-commit:  ## Run all pre-commit hooks against all files.
	pre-commit run --all-files

security-scan:  ## Run bandit security scanner.
	bandit -r pramana -c pyproject.toml

clean:  ## Remove caches and build artifacts.
	rm -rf .ruff_cache .mypy_cache .pytest_cache htmlcov .coverage
	rm -rf build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

migrate:  ## Apply all pending Alembic migrations.
	alembic upgrade head

migrate-create:  ## Create a new Alembic migration. Usage: make migrate-create m="message"
	alembic revision --autogenerate -m "$(m)"

migrate-down:  ## Roll back one Alembic migration.
	alembic downgrade -1

# --factory, not a module-level `app`: constructing the application at import
# time would resolve Settings on import and fight the test suite, which builds a
# fresh create_app() per test with its own dependency overrides.
run:  ## Run the FastAPI app with auto-reload. Override with HOST=/PORT=.
	uvicorn --factory pramana.api.app:create_app --reload --host $(HOST) --port $(PORT)

# `worker` deliberately removed: there is no Celery application in this repo
# (pramana/tasks/ is an empty package) and audit archival is an idempotent script
# by design — see `make archive-audit`. A target that always fails implies a
# capability that does not exist. Restore it alongside a real Celery app.

status:  ## Regenerate the README status table from project-status.yaml.
	$(PYTHON) scripts/render_status.py

archive-audit:  ## Mirror pending audit rows to WORM storage. Add status=1 or dry=1 to inspect.
	$(PYTHON) scripts/archive_audit.py $(if $(status),--status,) $(if $(dry),--dry-run,)

grant-role:  ## Bootstrap a role out of band. Usage: make grant-role email=you@example.com [role=auditor]
	$(PYTHON) scripts/grant_role.py --email "$(email)" $(if $(role),--role "$(role)",)

check:  ## Run lint + type-check + tests (CI equivalent).
	$(MAKE) lint
	$(MAKE) type-check
	$(MAKE) test
