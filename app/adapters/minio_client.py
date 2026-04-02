"""Adapter cho MinIO - production ready."""

from minio import Minio
from minio.error import S3Error
import structlog
from io import BytesIO
from app.config.settings import settings
from app.core.logger import logger

class MinIOAdapter:
    def __init__(self):
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ROOT_USER,
            secret_key=settings.MINIO_ROOT_PASSWORD,
            secure=False,
        )
        self.bucket = settings.MINIO_BUCKET

    def ensure_bucket(self):
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                logger.info("MinIO bucket created", bucket=self.bucket)
        except Exception as e:
            logger.error("Failed to ensure MinIO bucket", bucket=self.bucket, error=str(e))
            raise

    async def upload_file(self, file_bytes: bytes, object_name: str, content_type: str = "application/octet-stream") -> str:
        """Upload và trả về full path trong MinIO."""
        try:
            self.ensure_bucket()
            data_stream = BytesIO(file_bytes)
            self.client.put_object(
                self.bucket,
                object_name,
                data=data_stream,
                length=len(file_bytes),
                content_type=content_type,
            )
            logger.info("File uploaded to MinIO", object_name=object_name)
            return f"{self.bucket}/{object_name}"
        except S3Error as e:
            logger.error("MinIO upload failed", error=str(e), object_name=object_name)
            raise