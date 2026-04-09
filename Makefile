.PHONY: help lint format test test-cov dev build migrate

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

dev: ## Start development server + frontend watchers
	npm run dev & python3 manage.py runserver

build: ## Build frontend assets for production
	npm run build

migrate: ## Run database migrations
	python3 manage.py migrate

check: lint test test-js ## Run all checks (lint + test)
