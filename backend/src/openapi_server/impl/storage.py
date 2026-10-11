"""Image storage backends.

Product images are the only binary assets in the system. `local` keeps the
development and test behaviour (files under `MEDIA_ROOT`); `s3` stores the same
keys in an S3-compatible bucket, which is what a serverless or container
deployment needs because function filesystems are read-only and ephemeral.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Protocol

from openapi_server.impl.config import Settings

_CONTENT_TYPES = {
    ".webp": "image/webp",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class StorageError(RuntimeError):
    """Upload failed. Ingest skips the row instead of aborting the run."""


def content_type_for(key: str) -> str:
    return _CONTENT_TYPES.get(Path(key).suffix.lower(), "application/octet-stream")


class Storage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def local_path(self, key: str) -> Path | None: ...

    def presigned_url(self, key: str) -> str | None: ...


class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError(f"storage key escapes MEDIA_ROOT: {key!r}")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def local_path(self, key: str) -> Path | None:
        path = self._path(key)
        return path if path.is_file() else None

    def presigned_url(self, key: str) -> str | None:
        return None


class S3Storage:
    """Works with AWS S3, MinIO, Cloudflare R2 and Supabase Storage."""

    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self.prefix = settings.s3_key_prefix
        self.endpoint_url = settings.s3_endpoint_url or None
        # Inside a container network the API reaches the bucket by service
        # name, while the browser needs the host-published address. Only the
        # presigned URL (which the browser follows) uses the public endpoint.
        self.public_endpoint_url = settings.s3_public_endpoint_url or self.endpoint_url
        self.region = settings.s3_region
        self.access_key_id = settings.s3_access_key_id
        self.secret_access_key = settings.s3_secret_access_key
        self.presign_ttl = settings.s3_presign_ttl_seconds
        self._client = None
        self._presign_client = None
        self._lock = threading.Lock()

    def _build_client(self, endpoint_url: str | None):
        import boto3
        from botocore.config import Config

        return boto3.client(
            "s3",
            region_name=self.region,
            endpoint_url=endpoint_url,
            aws_access_key_id=self.access_key_id or None,
            aws_secret_access_key=self.secret_access_key or None,
            config=Config(
                signature_version="s3v4",
                s3={
                    # Custom endpoints (MinIO, R2, Supabase Storage) do not
                    # resolve bucket subdomains.
                    "addressing_style": "path" if endpoint_url else "auto"
                },
            ),
        )

    @property
    def client(self):
        with self._lock:
            if self._client is None:
                self._client = self._build_client(self.endpoint_url)
            return self._client

    @property
    def presign_client(self):
        with self._lock:
            if self._presign_client is None:
                self._presign_client = self._build_client(self.public_endpoint_url)
            return self._presign_client

    def object_key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def put(self, key: str, data: bytes) -> None:
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=self.object_key(key),
                Body=data,
                ContentType=content_type_for(key),
                CacheControl="private, max-age=60",
            )
        except Exception as exc:  # botocore errors are not OSError subclasses
            raise StorageError(f"upload failed for {key}: {exc}") from exc

    def local_path(self, key: str) -> Path | None:
        return None

    def presigned_url(self, key: str) -> str | None:
        try:
            return self.presign_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": self.object_key(key)},
                ExpiresIn=self.presign_ttl,
            )
        except Exception as exc:
            raise StorageError(f"presign failed for {key}: {exc}") from exc


def get_storage(settings: Settings) -> Storage:
    if settings.media_backend == "s3":
        return _s3_storage(settings)
    return LocalStorage(settings.media_root)


_s3_storages: dict[tuple, S3Storage] = {}


def _s3_storage(settings: Settings) -> S3Storage:
    """One boto3 client per configuration: it holds a connection pool."""
    key = (
        settings.s3_bucket,
        settings.s3_region,
        settings.s3_endpoint_url,
        settings.s3_public_endpoint_url,
        settings.s3_access_key_id,
        settings.s3_secret_access_key,
        settings.s3_key_prefix,
        settings.s3_presign_ttl_seconds,
    )
    storage = _s3_storages.get(key)
    if storage is None:
        storage = S3Storage(settings)
        _s3_storages[key] = storage
    return storage
