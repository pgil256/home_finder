.PHONY: help lint format test test-cov e2e-smoke dev build migrate

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

lint: ## Run linters (Python + JS)
	ruff check apps/ home_finder/
	npx eslint static/js/dev/ --ext .js

format: ## Auto-format code
	ruff format apps/ home_finder/
	ruff check --fix apps/ home_finder/

test: ## Run Python tests
	python -m pytest

test-cov: ## Run tests with coverage report
	python -m pytest --cov-report=html

test-js: ## Run JavaScript tests
	npm test

e2e-smoke: ## Run E2E smoke tests against deployed app (set E2E_BASE_URL to override)
	python -m pytest tests/e2e/test_smoke.py -v --no-header -p no:cacheprovider

e2e-functional: ## Run E2E functional tests (POSTs real scrapes; needs E2E_DATABASE_URL)
	python -m pytest tests/e2e/test_functional.py -v --no-header -p no:cacheprovider

e2e-browser: ## Run E2E browser tests via Playwright (headless)
	python -m pytest tests/e2e/browser/ -v --no-header -p no:cacheprovider

e2e-all: e2e-smoke e2e-functional e2e-browser ## Run all E2E suites in sequence

dev: ## Start development server + frontend watchers
	npm run dev & python3 manage.py runserver

build: ## Build frontend assets for production
	npm run build

migrate: ## Run database migrations
	python3 manage.py migrate

check: lint test test-js ## Run all checks (lint + test)
