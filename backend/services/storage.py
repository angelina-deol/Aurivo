"""
Object storage abstraction for uploaded audio.

Defaults to local disk (LOCAL_STORAGE_DIR) so Phase 2 works with zero
external setup. Set S3_ACCESS_KEY/S3_SECRET_KEY (and optionally
S3_ENDPOINT_URL for MinIO/R2/etc — leave it unset for real AWS S3) to switch
to S3-compatible storage without changing any calling code.
"""
import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO

from backend.config import get_settings

settings = get_settings()


class StorageBackend(ABC):
    @abstractmethod
    def save(self, file_obj: BinaryIO, key: str) -> str:
        """Persist file_obj under `key`. Returns a storage key/path that
        can be used later to retrieve or delete it."""

    @abstractmethod
    def delete(self, key: str) -> None:
        ...

    @abstractmethod
    def url_for(self, key: str) -> str:
        """Return a URL/path the rest of the app can use to fetch the file."""


class LocalDiskStorage(StorageBackend):
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Guard against path traversal — key is always a UUID-prefixed name
        # we generate ourselves, but defense in depth is cheap.
        safe_key = os.path.basename(key)
        return self.base_dir / safe_key

    def save(self, file_obj: BinaryIO, key: str) -> str:
        path = self._path(key)
        with open(path, "wb") as out:
            file_obj.seek(0)
            out.write(file_obj.read())
        return key

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def url_for(self, key: str) -> str:
        return str(self._path(key))


class S3CompatibleStorage(StorageBackend):
    def __init__(self):
        import boto3  # imported lazily so local-disk-only setups don't need it

        self._bucket = settings.S3_BUCKET
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
        )

    def save(self, file_obj: BinaryIO, key: str) -> str:
        file_obj.seek(0)
        self._client.upload_fileobj(file_obj, self._bucket, key)
        return key

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def url_for(self, key: str) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=3600,
        )


def get_storage_backend() -> StorageBackend:
    if settings.S3_ACCESS_KEY and settings.S3_SECRET_KEY:
        return S3CompatibleStorage()
    return LocalDiskStorage(settings.LOCAL_STORAGE_DIR)


def build_storage_key(original_filename: str) -> str:
    """Generates a collision-proof storage key that preserves the extension."""
    ext = Path(original_filename).suffix.lower()
    return f"{uuid.uuid4()}{ext}"
