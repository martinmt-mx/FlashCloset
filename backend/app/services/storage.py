"""Where generated images live.

Behind an interface from the start so moving to S3 later is a config change rather
than a rewrite of every call site. Local disk is right while the app runs on one
machine; hosted, the disk is wiped on every redeploy, so the files go to object
storage and only their URLs stay in the database.
"""

from __future__ import annotations

import mimetypes
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import cost only matters at runtime
    from app.config import Settings


class StorageBackend(ABC):
    @abstractmethod
    def save(self, content: bytes, suffix: str, folder: str = "") -> str:
        """Store bytes and return the URL the frontend should request."""


class LocalStorage(StorageBackend):
    def __init__(self, root: Path, base_url: str = "/media") -> None:
        self._root = root
        self._base_url = base_url.rstrip("/")
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, content: bytes, suffix: str, folder: str = "") -> str:
        name = f"{uuid.uuid4().hex}{suffix}"
        directory = self._root / folder if folder else self._root
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_bytes(content)
        return f"{self._base_url}/{folder}/{name}" if folder else f"{self._base_url}/{name}"


class S3Storage(StorageBackend):
    """Any S3-compatible bucket; used with Cloudflare R2, which bills no egress.

    `public_base_url` is what the browser fetches, so it is the bucket's public
    domain rather than the endpoint used to upload. The two differ on R2, and
    getting them mixed up produces URLs that only work from the server.
    """

    def __init__(
        self,
        bucket: str,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        public_base_url: str,
        region: str = "auto",
    ) -> None:
        import boto3  # imported here so local runs need no AWS dependency

        self._bucket = bucket
        self._public_base_url = public_base_url.rstrip("/")
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    def save(self, content: bytes, suffix: str, folder: str = "") -> str:
        name = f"{uuid.uuid4().hex}{suffix}"
        key = f"{folder}/{name}" if folder else name
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=content,
            ContentType=mimetypes.types_map.get(suffix, "application/octet-stream"),
            # These are immutable: every save invents a fresh name, so nothing at a
            # given URL ever changes and the browser can keep it forever.
            CacheControl="public, max-age=31536000, immutable",
        )
        return f"{self._public_base_url}/{key}"

    def put_at(self, key: str, content: bytes, suffix: str) -> str:
        """Upload to an exact key instead of a generated one, for migrating files
        whose URLs are already recorded in the database."""
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=content,
            ContentType=mimetypes.types_map.get(suffix, "application/octet-stream"),
            CacheControl="public, max-age=31536000, immutable",
        )
        return f"{self._public_base_url}/{key}"


def build_storage(settings: "Settings") -> StorageBackend:
    """Pick the backend named by configuration, failing loudly on a half-set one.

    A missing S3 variable in production would otherwise fall back to local disk and
    silently write files that vanish on the next redeploy.
    """
    if settings.storage_backend != "s3":
        return LocalStorage(settings.media_dir)

    missing = [
        name
        for name, value in (
            ("R2_BUCKET", settings.r2_bucket),
            ("R2_ENDPOINT_URL", settings.r2_endpoint_url),
            ("R2_ACCESS_KEY_ID", settings.r2_access_key_id),
            ("R2_SECRET_ACCESS_KEY", settings.r2_secret_access_key),
            ("R2_PUBLIC_BASE_URL", settings.r2_public_base_url),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "STORAGE_BACKEND=s3 but these are unset: " + ", ".join(missing)
        )

    return S3Storage(
        bucket=settings.r2_bucket,
        endpoint_url=settings.r2_endpoint_url,
        access_key=settings.r2_access_key_id,
        secret_key=settings.r2_secret_access_key,
        public_base_url=settings.r2_public_base_url,
    )
