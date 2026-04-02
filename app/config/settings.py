"""Config loader production-ready sử dụng Pydantic Settings v2."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List
import json

class Settings(BaseSettings):
    """Cấu hình toàn bộ ứng dụng. Đọc tự động từ .env và environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    APP_NAME: str = "GraphRAG Pentest Platform"

    # Database
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Neo4j
    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str

    # Weaviate
    WEAVIATE_URL: str = "http://weaviate:8080"
    WEAVIATE_API_KEY: str = ""  # anonymous cho lab

    # MinIO
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ROOT_USER: str
    MINIO_ROOT_PASSWORD: str
    MINIO_BUCKET: str = "graphrag-bucket"

    # Security & Lab Safety
    ALLOWED_TARGETS: List[str] = ["127.0.0.1", "localhost"]
    MAX_TOOL_TIMEOUT: int = 300
    RATE_LIMIT_PER_MIN: int = 30

    # Ollama (sẽ dùng Phase 5)
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"
    EMBEDDING_MODEL: str = "nomic-embed-text-v1.5"

    @field_validator("ALLOWED_TARGETS", mode="before")
    @classmethod
    def parse_allowed_targets(cls, value):
        """Accept either JSON array or comma-separated values from env."""
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("["):
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in raw.split(",") if item.strip()]
        return value

    @property
    def postgres_dsn(self) -> str:
        """PostgreSQL DSN cho SQLAlchemy."""
        # Debug: print the values
        print(f"DEBUG: POSTGRES_USER={self.POSTGRES_USER}, POSTGRES_DB={self.POSTGRES_DB}")
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    def is_target_allowed(self, target: str) -> bool:
        """Kiểm tra whitelist target – bắt buộc mọi tool wrapper sau này."""
        normalized = target.strip().lower()
        return any(normalized == t.strip().lower() for t in self.ALLOWED_TARGETS)

settings = Settings()