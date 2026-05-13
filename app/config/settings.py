"""Config loader production-ready sử dụng Pydantic Settings v2."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    """Cấu hình toàn bộ ứng dụng. Đọc tự động từ .env và environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    APP_NAME: str = "GraphRAG Pentest Platform"

    # Database
    POSTGRES_DB: str = "pentest_graphrag"
    POSTGRES_USER: str = "graphrag_user"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Neo4j
    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    # Weaviate
    WEAVIATE_URL: str = "http://weaviate:8080"
    WEAVIATE_API_KEY: str = ""

    # MinIO
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ROOT_USER: str = "minioadmin"
    MINIO_ROOT_PASSWORD: str = "minioadmin"
    MINIO_BUCKET: str = "graphrag-bucket"

    # Elasticsearch (Phase 5.3)
    ELASTICSEARCH_HOSTS: str = "localhost:9200"
    ELASTICSEARCH_USER: str = ""
    ELASTICSEARCH_PASSWORD: str = ""

    # JWT Authentication (Phase 5.4)
    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production-immediately"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Security & Lab Safety
    ALLOWED_TARGETS: str = "127.0.0.1,localhost"
    MAX_TOOL_TIMEOUT: int = 300
    RATE_LIMIT_PER_MIN: int = 30

    # Ollama (Phase 5)
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "llama3.2:3b"
    EMBEDDING_MODEL: str = "nomic-embed-text-v1.5"

    # Nuclei (Phase 9)
    NUCLEI_ENDPOINT: str = "http://nuclei:8080"
    NUCLEI_TIMEOUT: int = 300

    # Weaviate connection (Phase 10 fix)
    WEAVIATE_HOST: str = "weaviate"
    WEAVIATE_PORT: int = 8080
    WEAVIATE_GRPC_PORT: int = 50051

    # ── Tunable parameters (Phase 10-13) ──────────────────────────────────
    # RRF Retrieval
    RRF_ALPHA: float = 0.3      # 0.0=pure graph  1.0=pure vector  (optimal=0.3 per benchmark)
    RRF_K: float = 60.0         # RRF constant (higher→smoother rank diff)

    # LLM Extraction confidence gates
    ENTITY_CONFIDENCE_THRESHOLD: float = 0.85
    RELATION_CONFIDENCE_THRESHOLD: float = 0.75

    # KG Completion (Phase 11)
    KG_MIN_CONFIDENCE: float = 0.65
    KG_MAX_DEGREE: int = 2      # entities with ≤ this many edges get completed

    # GNN Risk weights (must sum to 1.0) (Phase 12)
    # w_sev=0.80: CVSS/severity là ground truth chính trong pentest context
    # w_pr=0.10: graph centrality dùng làm tie-breaker giữa các nodes cùng severity
    GNN_W_PAGERANK: float = 0.10
    GNN_W_SEVERITY: float = 0.80
    GNN_W_BETWEENNESS: float = 0.10

    # Workflow feedback loop (Phase 10)
    MAX_LOOP_ITERATIONS: int = 3

    # Nmap collection (Phase 10)
    NMAP_OPTIONS: str = "-sV,-sC,--top-ports,1000"   # comma-separated flags

    # Attack-path depth (Phase 12)
    ATTACK_PATH_MAX_HOPS: int = 4

    @property
    def postgres_dsn(self) -> str:
        """PostgreSQL DSN cho SQLAlchemy."""
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    def is_target_allowed(self, target: str) -> bool:
        """Kiểm tra whitelist target – bắt buộc mọi tool wrapper sau này."""
        normalized = target.strip().lower()
        allowed_list = [t.strip().lower() for t in self.ALLOWED_TARGETS.split(",") if t.strip()]
        return normalized in allowed_list

settings = Settings()