from io import BytesIO
from typing import Protocol, cast
from urllib.parse import urlparse

from minio import Minio
from minio.helpers import DictType

from app.core.config import get_settings


class ObjectStorage(Protocol):
    def put_object(
        self,
        *,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str | None,
        metadata: dict[str, str],
    ) -> None: ...

    def get_object(self, *, bucket: str, key: str) -> bytes: ...


class MinioObjectStorage:
    def __init__(self) -> None:
        settings = get_settings()
        endpoint = normalize_minio_endpoint(settings.minio_endpoint)
        self.client = Minio(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def put_object(
        self,
        *,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str | None,
        metadata: dict[str, str],
    ) -> None:
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)

        self.client.put_object(
            bucket,
            key,
            BytesIO(data),
            length=len(data),
            content_type=content_type or "application/octet-stream",
            metadata=cast(DictType, metadata),
        )

    def get_object(self, *, bucket: str, key: str) -> bytes:
        response = self.client.get_object(bucket, key)
        try:
            return bytes(response.read())
        finally:
            response.close()
            response.release_conn()


def normalize_minio_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme:
        return parsed.netloc
    return endpoint


def get_object_storage() -> ObjectStorage:
    return MinioObjectStorage()
