# Pramana developer Makefile.
# Run `make help` for available targets.

.PHONY: help install dev-install lint format type-check test test-cov \
        pre-commit clean migrate migrate-create run worker security-scan

PYTHON := python3
PIP := $(PYTHON) -m pip

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

run:  ## Run the FastAPI app locally with auto-reload.
	uvicorn pramana.api.main:app --reload --host 0.0.0.0 --port 8000

worker:  ## Run a Celery worker.
	celery -A pramana.tasks worker --loglevel=info

check:  ## Run lint + type-check + tests (CI equivalent).
	$(MAKE) lint
	$(MAKE) type-check
	$(MAKE) test
