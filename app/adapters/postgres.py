"""SQLAlchemy adapter + models - Phase 4."""

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON, ForeignKey, func
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from app.config.settings import settings

Base = declarative_base()

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String, nullable=False)
    content_type = Column(String)
    minio_path = Column(String, unique=True, nullable=False)
    doc_metadata = Column(JSON, default={})
    hash = Column(String, unique=True)
    chunks_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")

class Chunk(Base):
    __tablename__ = "chunks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    chunk_metadata = Column(JSON, default={})
    weaviate_uuid = Column(UUID(as_uuid=True), nullable=True)
    hash = Column(String, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("Document", back_populates="chunks")

# ==================== Phase 3: Nuclei Findings Tables ====================

class NucleiScan(Base):
    """Nuclei scan metadata and status tracking."""
    __tablename__ = "nuclei_scans"
    
    id = Column(String, primary_key=True, default=lambda: str(__import__('uuid').uuid4()))
    target_url = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending, running, completed, failed
    findings_count = Column(Integer, default=0)
    scan_type = Column(String, default="full")  # full, web, api
    raw_output_path = Column(String, nullable=True)
    neo4j_status = Column(String, default="pending")  # pending, upserted, failed
    neo4j_error = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    scan_metadata = Column(JSON, default={})  # Renamed from 'metadata' to avoid SQLAlchemy conflict
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    findings = relationship("NucleiFindings", back_populates="scan", cascade="all, delete-orphan")


class NucleiFindings(Base):
    """Individual findings from Nuclei scans."""
    __tablename__ = "nuclei_findings"
    
    id = Column(String, primary_key=True, default=lambda: str(__import__('uuid').uuid4()))
    scan_id = Column(String, ForeignKey("nuclei_scans.id", ondelete="CASCADE"), nullable=False)
    finding_id = Column(String, nullable=False)  # UUID from parser
    template_id = Column(String, nullable=False)
    severity = Column(String, nullable=False)  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    host = Column(String, nullable=False)
    url = Column(String, nullable=False)
    matched_at = Column(DateTime(timezone=True), nullable=True)
    source = Column(String, default="nuclei")
    cve_ids = Column(JSON, default=[])  # List of CVE IDs
    cwe_ids = Column(JSON, default=[])  # List of CWE IDs
    finding_metadata = Column(JSON, default={})  # Renamed from 'metadata' to avoid SQLAlchemy conflict
    neo4j_id = Column(String, nullable=True)  # UUID of node in Neo4j
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    scan = relationship("NucleiScan", back_populates="findings")


# ==================== Phase 5: Job Queue Table ====================

class JobQueue(Base):
    """Background job queue for async task processing."""
    __tablename__ = "job_queue"
    
    id = Column(String, primary_key=True, default=lambda: str(__import__('uuid').uuid4()))
    job_id = Column(String, unique=True, nullable=False)  # Celery task ID
    job_type = Column(String, nullable=False)  # nuclei_scan, batch_scan, neo4j_upsert, etc.
    status = Column(String, default="pending")  # pending, running, completed, failed, cancelled, retrying
    priority = Column(Integer, default=5)  # 1-10, higher = more urgent
    target_url = Column(String, nullable=True)
    payload = Column(JSON, nullable=True)  # Input parameters
    result = Column(JSON, nullable=True)  # Job result/output
    error_message = Column(String, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    callback_url = Column(String, nullable=True)  # Webhook for completion
    job_metadata = Column(JSON, default={})  # Job metadata (renamed from 'metadata' to avoid SQLAlchemy conflict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    __table_args__ = (
        __import__('sqlalchemy').CheckConstraint('priority BETWEEN 1 AND 10'),
        __import__('sqlalchemy').CheckConstraint('retry_count <= max_retries'),
    )


# ==================== Phase 5.4: Authentication & Authorization ====================

class User(Base):
    """User account for authentication (Phase 5.4)."""
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(__import__('uuid').uuid4()))
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="viewer", nullable=False)  # admin, analyst, operator, viewer
    is_active = Column(__import__('sqlalchemy').Boolean, default=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class APIKey(Base):
    """API keys for service-to-service authentication (Phase 5.4)."""
    __tablename__ = "api_keys"
    
    id = Column(String, primary_key=True, default=lambda: str(__import__('uuid').uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    key_hash = Column(String, unique=True, nullable=False)  # Hashed API key
    permissions = Column(JSON, default=[], nullable=False)  # Array of permission strings
    is_active = Column(__import__('sqlalchemy').Boolean, default=True)
    last_used = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Audit log for security and compliance (Phase 5.4)."""
    __tablename__ = "audit_logs"
    
    id = Column(String, primary_key=True, default=lambda: str(__import__('uuid').uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String, nullable=False, index=True)  # login, create_job, delete_job, etc
    resource = Column(String, nullable=True, index=True)  # job_id, user_id, etc
    status = Column(String, default="success")  # success or failure
    details = Column(JSON, default={}, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)


# ==================== Phase 5.5: Batch Operations ====================

class BatchJob(Base):
    """Batch job for managing multiple targets (Phase 5.5)."""
    __tablename__ = "batch_jobs"
    
    id = Column(String, primary_key=True, default=lambda: str(__import__('uuid').uuid4()))
    batch_name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String, default="pending")  # pending, processing, completed, failed
    total_targets = Column(Integer, default=0)
    completed_targets = Column(Integer, default=0)
    failed_targets = Column(Integer, default=0)
    job_ids = Column(JSON, default=[], nullable=False)  # Array of job IDs in this batch
    results = Column(JSON, default={}, nullable=True)  # Aggregated results
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


# Engine
async_engine = create_async_engine(
    settings.postgres_dsn.replace("postgresql+psycopg2", "postgresql+asyncpg"),
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session