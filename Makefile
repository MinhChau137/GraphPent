.PHONY: help up down restart clean logs-backend logs-all health test test-coverage load-sample bootstrap

# Enable BuildKit for faster builds
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

help:
	@echo "📋 GraphRAG Makefile Commands"
	@echo "=============================="
	@echo "make up              - Start all services"
	@echo "make down            - Stop all services"
	@echo "make restart         - Restart all services"
	@echo "make clean           - Clean everything and rebuild"
	@echo "make logs-backend    - View backend logs"
	@echo "make logs-all        - View all logs"
	@echo "make health          - Check health endpoint"
	@echo "make test            - Run tests"
	@echo "make test-coverage   - Run tests with coverage"
	@echo "make load-sample     - Load sample data"
	@echo "make bootstrap       - Bootstrap all services"

up:
	@echo "🚀 Starting services with BuildKit enabled..."
	docker compose up --build -d
	@echo "✅ Services starting... Wait ~1-2 minutes for all services to be healthy"
	@echo "📊 Check status: docker compose ps"
	@echo "📋 View logs: make logs-backend"

down:
	@echo "⏹️  Stopping services..."
	docker compose down -v
	@echo "✅ Services stopped"

restart: down up
	@echo "🔄 Services restarted"

clean:
	@echo "🧹 Cleaning everything..."
	docker compose down -v
	docker system prune -a --volumes -f
	@echo "✅ Cleaned. Running fresh build..."
	docker compose up --build -d
	@echo "✅ Fresh build complete"

logs-backend:
	docker compose logs -f backend

logs-all:
	docker compose logs -f

health:
	@curl -s http://localhost:8000/health | python -m json.tool
	@echo ""

bootstrap: bootstrap-postgres bootstrap-neo4j bootstrap-weaviate bootstrap-minio
	@echo "✅ Bootstrap complete"

bootstrap-postgres:
	@echo "PostgreSQL init auto run when container starts at the first time"

bootstrap-neo4j:
	@scripts\bootstrap\bootstrap_neo4j.bat

bootstrap-weaviate:
	docker compose exec backend python /app/scripts/bootstrap/weaviate_bootstrap.py

bootstrap-minio:
	docker compose exec backend python /app/scripts/bootstrap/minio_bootstrap.py

test:
	pytest tests/ -v --asyncio-mode=auto

test-coverage:
	pytest tests/ --cov=app --cov-report=term-missing

load-sample:
	python scripts/fixtures/load_sample_data.py

build-only:
	@echo "Building without starting services..."
	docker compose build --progress=plain

logs-ollama:
	docker compose logs -f ollama

logs-postgres:
	docker compose logs -f postgres

status:
	docker compose ps
	@echo ""
	@echo "Port Summary:"
	@echo "  Backend: http://localhost:8000"
	@echo "  Ollama:  http://localhost:9443"
	@echo "  Neo4j:   http://localhost:7474"
	@echo "  Weaviate: http://localhost:8080"
	@echo "  MinIO:   http://localhost:9001"
	@echo "  Postgres: localhost:5432"