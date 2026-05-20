.PHONY: help dev lint format typecheck test test-cov docker-up docker-down clean

help:
	@echo "dev         - Start dev server with hot reload"
	@echo "lint        - Run Ruff linter"
	@echo "format      - Run Black formatter"
	@echo "typecheck   - Run MyPy type checker"
	@echo "test        - Run test suite"
	@echo "test-cov    - Run tests with coverage"
	@echo "docker-up   - Start all services via docker compose"
	@echo "docker-down - Stop all services"
	@echo "clean       - Remove __pycache__ and .pytest_cache"

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

lint:
	ruff check .
	ruff format --check .

format:
	black .
	ruff format .

typecheck:
	mypy app/

test:
	pytest tests/

test-cov:
	pytest --cov=app --cov-report=term-missing tests/

docker-up:
	docker compose -f docker/docker-compose.yml up -d

docker-down:
	docker compose -f docker/docker-compose.yml down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
