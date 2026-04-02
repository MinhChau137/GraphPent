.PHONY: up down bootstrap clean

up:
	docker compose up --build -d

down:
	docker compose down -v

bootstrap: bootstrap-postgres bootstrap-neo4j bootstrap-weaviate bootstrap-minio

bootstrap-postgres:
	@echo "PostgreSQL init auto run when container start at the first time"

bootstrap-neo4j:
	@scripts\bootstrap\bootstrap_neo4j.bat

bootstrap-weaviate:
	docker compose exec backend python /scripts/bootstrap/weaviate_bootstrap.py

bootstrap-minio:
	docker compose exec backend python /scripts/bootstrap/minio_bootstrap.py

logs-backend:
	docker compose logs -f backend

health:
	curl http://localhost:8000/health