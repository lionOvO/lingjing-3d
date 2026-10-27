"""Object storage integration for source images and generated artifacts."""
from __future__ import annotations

import io
import asyncio
import logging
import re
import uuid
from datetime import timedelta
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse

from fastapi import UploadFile
import httpx

from .config import settings

logger = logging.getLogger("digital_human.storage")
ALLOWED_IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class StorageError(RuntimeError):
    """Raised when object storage cannot accept or serve an upload."""


@dataclass(frozen=True)
class StoredObject:
    object_name: str
    url: str
    size: int
    content_type: str


class ObjectStorage:
    """MinIO adapter. All blocking SDK operations are run off the event loop."""

    def __init__(self, client: Any | None = None, *, bucket: str | None = None):
        self.bucket = bucket or settings.minio_bucket
        self.client = client
        if self.client is None:
            try:
                from minio import Minio
                self.client = Minio(settings.minio_endpoint, access_key=settings.minio_access_key, secret_key=settings.minio_secret_key, secure=settings.minio_secure)
            except Exception as exc:
                logger.warning("MinIO SDK unavailable", exc_info=True)
                self.client = None

    async def upload_image(self, upload: UploadFile, *, prefix: str = "uploads") -> StoredObject:
        content_type = (upload.content_type or "").lower().split(";", 1)[0].strip()
        suffix = self._validate_type(upload.filename or "", content_type)
        max_bytes = settings.upload_max_size_mb * 1024 * 1024
        data = bytearray()
        while True:
            chunk = await upload.read(min(1024 * 1024, max_bytes + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > max_bytes:
                raise StorageError(f"Image exceeds {settings.upload_max_size_mb}MB limit")
        if not data:
            raise StorageError("Uploaded image is empty")
        if self.client is None:
            raise StorageError("Object storage is not configured")
        object_name = f"{prefix.strip('/')}/{uuid.uuid4().hex}{suffix}"
        try:
            await self._ensure_bucket()
            await asyncio.to_thread(self.client.put_object, self.bucket, object_name, io.BytesIO(bytes(data)), len(data), content_type=content_type)
            url = await self._presigned_url(object_name)
            logger.info("Stored uploaded image object=%s size=%s", object_name, len(data))
            return StoredObject(object_name, url, len(data), content_type)
        except Exception as exc:
            logger.exception("MinIO image upload failed object=%s", object_name)
            raise StorageError("Image storage service is unavailable") from exc

    async def upload_url(self, url: str, *, prefix: str = "uploads") -> StoredObject:
        """Fetch a remote image with the same type/size checks as multipart upload."""
        try:
            async with httpx.AsyncClient(timeout=settings.agent_http_timeout, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                filename = url.rsplit("/", 1)[-1].split("?", 1)[0] or "remote.png"
                suffix = self._validate_type(filename, content_type)
                data = response.content
        except StorageError:
            raise
        except Exception as exc:
            logger.exception("Remote image fetch failed url=%s", url)
            raise StorageError("Unable to fetch source image URL") from exc
        max_bytes = settings.upload_max_size_mb * 1024 * 1024
        if not data or len(data) > max_bytes:
            raise StorageError(f"Image exceeds {settings.upload_max_size_mb}MB limit or is empty")
        if self.client is None:
            raise StorageError("Object storage is not configured")
        object_name = f"{prefix.strip('/')}/{uuid.uuid4().hex}{suffix}"
        try:
            await self._ensure_bucket()
            await asyncio.to_thread(self.client.put_object, self.bucket, object_name, io.BytesIO(data), len(data), content_type=content_type or "image/png")
            return StoredObject(object_name, await self._presigned_url(object_name), len(data), content_type or "image/png")
        except Exception as exc:
            logger.exception("MinIO remote image upload failed object=%s", object_name)
            raise StorageError("Image storage service is unavailable") from exc

    async def delete(self, object_name: str) -> None:
        if self.client is None:
            return
        try:
            await asyncio.to_thread(self.client.remove_object, self.bucket, object_name)
        except Exception:
            logger.warning("Failed to remove orphaned object=%s", object_name, exc_info=True)

    async def upload_generated_model(self, task_id: int, data: bytes, output_format: str) -> str:
        """Persist an engine artifact and return its private object name.

        Generated files are delivered through the API instead of exposing the
        internal MinIO hostname to browsers outside Docker's data network.
        """
        if not data:
            raise StorageError("Generated model is empty")
        if self.client is None:
            raise StorageError("Object storage is not configured")
        suffix = output_format.lower().lstrip(".")
        if suffix not in {"glb", "obj", "fbx", "stl"}:
            raise StorageError("Unsupported generated model format")
        object_name = f"generated/{task_id}/{uuid.uuid4().hex}.{suffix}"
        content_type = "model/gltf-binary" if suffix == "glb" else "application/octet-stream"
        try:
            await self._ensure_bucket()
            await asyncio.to_thread(
                self.client.put_object,
                self.bucket,
                object_name,
                io.BytesIO(data),
                len(data),
                content_type=content_type,
            )
            logger.info("Stored generated model task_id=%s object=%s size=%s", task_id, object_name, len(data))
            return object_name
        except Exception as exc:
            logger.exception("Generated model storage failed task_id=%s object=%s", task_id, object_name)
            raise StorageError("Generated model storage service is unavailable") from exc

    async def get_object(self, object_name: str) -> tuple[bytes, str]:
        """Read a private object for authenticated API delivery."""
        if self.client is None:
            raise StorageError("Object storage is not configured")
        try:
            response = await asyncio.to_thread(self.client.get_object, self.bucket, object_name)
            try:
                data = await asyncio.to_thread(response.read)
                content_type = getattr(response, "headers", {}).get("content-type", "application/octet-stream")
            finally:
                await asyncio.to_thread(response.close)
                await asyncio.to_thread(response.release_conn)
            return data, content_type
        except Exception as exc:
            logger.exception("Object read failed object=%s", object_name)
            raise StorageError("Generated model is unavailable") from exc

    def object_name_from_url(self, value: str | None) -> str | None:
        """Extract an object name only from this application's MinIO URLs.

        Source images are stored as presigned URLs, but those URLs contain the
        Docker-only MinIO hostname.  This parser deliberately rejects other
        hosts and paths so the API cannot become an arbitrary URL fetcher.
        """
        if not value:
            return None
        parsed = urlparse(value)
        configured_host = settings.minio_endpoint.split(":", 1)[0].lower()
        if parsed.hostname and parsed.hostname.lower() != configured_host:
            return None
        path = unquote(parsed.path).lstrip("/")
        bucket_prefix = f"{self.bucket}/"
        if not path.startswith(bucket_prefix):
            return None
        object_name = path[len(bucket_prefix):]
        return object_name or None

    async def _ensure_bucket(self) -> None:
        exists = await asyncio.to_thread(self.client.bucket_exists, self.bucket)
        if not exists:
            await asyncio.to_thread(self.client.make_bucket, self.bucket)

    async def _presigned_url(self, object_name: str) -> str:
        try:
            return await asyncio.to_thread(self.client.presigned_get_object, self.bucket, object_name, expires=timedelta(days=7))
        except Exception:
            scheme = "https" if settings.minio_secure else "http"
            return f"{scheme}://{settings.minio_endpoint}/{self.bucket}/{object_name}"

    @staticmethod
    def _validate_type(filename: str, content_type: str) -> str:
        suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if content_type not in ALLOWED_IMAGE_TYPES and suffix not in ALLOWED_EXTENSIONS:
            raise StorageError("Only PNG, JPG/JPEG and WEBP images are supported")
        return ALLOWED_IMAGE_TYPES.get(content_type, ".jpg" if suffix == ".jpeg" else suffix)


def safe_filename(filename: str) -> str:
    """Return a log-safe basename; object names never trust user path segments."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", filename.rsplit("\\", 1)[-1].rsplit("/", 1)[-1])[:255]


storage = ObjectStorage()
