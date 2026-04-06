"""Ingestion service chính - Phase 4."""

import hashlib
from sqlalchemy import select
from app.adapters.minio_client import MinIOAdapter
from app.adapters.postgres import Document, Chunk, AsyncSessionLocal
from app.utils.parsers import parse_document
from app.utils.chunking import chunk_text
from app.core.logger import logger
from app.core.security import audit_log
from uuid import uuid4

class IngestionService:
    def __init__(self):
        self.minio = MinIOAdapter()

    async def ingest_document(self, file_bytes: bytes, filename: str, content_type: str, metadata: dict = None) -> dict:
        """Main ingestion pipeline."""
        await audit_log("ingest_document_start", {"filename": filename})

        # 1. Hash để dedup
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        async with AsyncSessionLocal() as session:
            # Kiểm tra tồn tại
            existing = await session.execute(select(Document).where(Document.hash == file_hash))
            existing_doc = existing.scalar_one_or_none()
            if existing_doc:
                logger.info("Ingestion completed", status="duplicate", document_id=existing_doc.id, filename=filename)
                return {
                    "document_id": existing_doc.id,
                    "filename": existing_doc.filename or filename,
                    "chunks_count": existing_doc.chunks_count or 0,
                    "status": "duplicate",
                    "message": "duplicate",
                    "ingestion_job_id": None,
                }

            # 2. Parse
            text = await parse_document(file_bytes, content_type, filename)

            # 3. Chunk
            chunks_data = await chunk_text(text)

            # 4. Upload MinIO
            object_name = f"raw/{uuid4()}_{filename}"
            minio_path = await self.minio.upload_file(file_bytes, object_name, content_type)

            # 5-6. Save document and chunks atomically to avoid partial ingestion.
            try:
                doc = Document(
                    filename=filename,
                    content_type=content_type,
                    minio_path=minio_path,
                    doc_metadata=metadata or {},
                    hash=file_hash,
                    chunks_count=len(chunks_data),
                )
                session.add(doc)
                await session.flush()

                for chunk in chunks_data:
                    chunk_hash = hashlib.sha256(
                        f"{file_hash}:{chunk['chunk_index']}:{chunk['content']}".encode("utf-8")
                    ).hexdigest()
                    chunk_obj = Chunk(
                        document_id=doc.id,
                        chunk_index=chunk["chunk_index"],
                        content=chunk["content"],
                        chunk_metadata=chunk["metadata"],
                        hash=chunk_hash,
                    )
                    session.add(chunk_obj)

                await session.commit()
            except Exception:
                await session.rollback()
                raise

            logger.info("Ingestion completed", status="success", document_id=doc.id, chunks=len(chunks_data))

            await audit_log("ingest_document_success", {"document_id": doc.id, "chunks": len(chunks_data)})

            return {
                "document_id": doc.id,
                "filename": filename,
                "chunks_count": len(chunks_data),
                "status": "success",
                "message": "Ingestion completed",
                "ingestion_job_id": str(uuid4()),
            }