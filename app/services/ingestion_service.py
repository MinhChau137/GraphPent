"""Ingestion service chính - Phase 4."""

import hashlib
from sqlalchemy import select, insert
from app.adapters.minio_client import MinIOAdapter
from app.adapters.postgres import Document, Chunk, AsyncSessionLocal
from app.utils.parsers import parse_document
from app.utils.chunking import chunk_text, generate_hash
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
            if existing.scalar_one_or_none():
                logger.info("Document already exists by hash", filename=filename)
                return {"status": "duplicate", "message": "Document already ingested"}

            # 2. Parse
            text = await parse_document(file_bytes, content_type, filename)

            # 3. Chunk
            chunks_data = await chunk_text(text)

            # 4. Upload MinIO
            object_name = f"raw/{uuid4()}_{filename}"
            minio_path = await self.minio.upload_file(file_bytes, object_name, content_type)

            # 5. Save Document to PostgreSQL
            doc = Document(
                filename=filename,
                content_type=content_type,
                minio_path=minio_path,
                doc_metadata=metadata or {},
                hash=file_hash,
            )
            session.add(doc)
            await session.commit()
            await session.refresh(doc)

            # 6. Save Chunks
            for chunk in chunks_data:
                chunk_obj = Chunk(
                    document_id=doc.id,
                    chunk_index=chunk["chunk_index"],
                    content=chunk["content"],
                    chunk_metadata=chunk["metadata"],
                    hash=chunk["hash"],
                )
                session.add(chunk_obj)

            await session.commit()

            logger.info("Ingestion completed", document_id=doc.id, chunks=len(chunks_data))

            await audit_log("ingest_document_success", {"document_id": doc.id, "chunks": len(chunks_data)})

            return {
                "document_id": doc.id,
                "filename": filename,
                "chunks_count": len(chunks_data),
                "status": "success",
                "ingestion_job_id": str(uuid4()),
            }