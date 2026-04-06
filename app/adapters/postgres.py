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