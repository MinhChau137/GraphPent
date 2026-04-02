#!/usr/bin/env python3
"""Phase 3: MinIO bucket bootstrap."""

from minio import Minio
from minio.error import S3Error
import os

# Load config from environment variables
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ROOT_USER = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_ROOT_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin123")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "graphrag-bucket")

client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ROOT_USER,
    secret_key=MINIO_ROOT_PASSWORD,
    secure=False,
)

bucket = MINIO_BUCKET
if not client.bucket_exists(bucket):
    client.make_bucket(bucket)
    print(f"✅ Created MinIO bucket: {bucket}")
else:
    print(f"✅ Bucket already exists: {bucket}")

# Optional policy (public read cho lab)
print("🎉 MinIO bootstrap completed")