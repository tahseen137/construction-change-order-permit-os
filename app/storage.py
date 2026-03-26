from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import boto3

from app.config import Settings


@dataclass
class StoredObject:
    storage_key: str
    size_bytes: int


class StorageClient:
    def store_bytes(self, *, workspace_slug: str, filename: str, content: bytes, content_type: str) -> StoredObject:
        raise NotImplementedError

    def read_bytes(self, storage_key: str) -> bytes:
        raise NotImplementedError


class LocalStorageClient(StorageClient):
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def store_bytes(self, *, workspace_slug: str, filename: str, content: bytes, content_type: str) -> StoredObject:
        safe_name = filename.replace("\\", "_").replace("/", "_")
        storage_key = f"{workspace_slug}/{uuid4()}-{safe_name}"
        target = self.base_dir / storage_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return StoredObject(storage_key=storage_key, size_bytes=len(content))

    def read_bytes(self, storage_key: str) -> bytes:
        return (self.base_dir / storage_key).read_bytes()


class S3StorageClient(StorageClient):
    def __init__(self, settings: Settings):
        self.bucket = settings.s3_bucket or ""
        self.client = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )

    def store_bytes(self, *, workspace_slug: str, filename: str, content: bytes, content_type: str) -> StoredObject:
        safe_name = filename.replace("\\", "_").replace("/", "_")
        storage_key = f"{workspace_slug}/{uuid4()}-{safe_name}"
        self.client.put_object(Bucket=self.bucket, Key=storage_key, Body=content, ContentType=content_type)
        return StoredObject(storage_key=storage_key, size_bytes=len(content))

    def read_bytes(self, storage_key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=storage_key)
        return response["Body"].read()


def build_storage_client(settings: Settings) -> StorageClient:
    if settings.storage_backend == "s3":
        return S3StorageClient(settings)
    return LocalStorageClient(settings.uploads_dir)
