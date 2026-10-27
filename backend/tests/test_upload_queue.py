from types import SimpleNamespace

import pytest

from app.storage import ObjectStorage, StorageError


class FakeUpload:
    def __init__(self, data: bytes, filename="source.png", content_type="image/png"):
        self.data = data
        self.filename = filename
        self.content_type = content_type
        self.offset = 0

    async def read(self, size=-1):
        if self.offset >= len(self.data):
            return b""
        if size < 0:
            size = len(self.data)
        chunk = self.data[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


class FakeMinio:
    def __init__(self):
        self.objects = []

    def bucket_exists(self, bucket):
        return True

    def put_object(self, bucket, name, stream, length, content_type):
        self.objects.append((bucket, name, stream.read(), length, content_type))

    def presigned_get_object(self, bucket, name, expires):
        return f"http://minio/{bucket}/{name}"

    def remove_object(self, bucket, name):
        return None


@pytest.mark.asyncio
async def test_upload_image_stores_object_and_returns_url():
    client = FakeMinio()
    result = await ObjectStorage(client=client, bucket="test").upload_image(FakeUpload(b"png-data"), prefix="projects/1")
    assert result.url.startswith("http://minio/test/projects/1/")
    assert result.size == 8
    assert client.objects[0][4] == "image/png"


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_type():
    with pytest.raises(StorageError):
        await ObjectStorage(client=FakeMinio()).upload_image(FakeUpload(b"x", "source.exe", "application/octet-stream"))


@pytest.mark.asyncio
async def test_upload_rejects_empty_file():
    with pytest.raises(StorageError):
        await ObjectStorage(client=FakeMinio()).upload_image(FakeUpload(b""))


@pytest.mark.asyncio
async def test_upload_endpoint_returns_minio_object(client, monkeypatch):
    from app import routers

    monkeypatch.setattr(routers, "storage", ObjectStorage(client=FakeMinio(), bucket="test"))
    response = await client.post("/api/v1/uploads", files={"image": ("avatar.png", b"png-data", "image/png")})
    assert response.status_code == 201
    body = response.json()
    assert body["size"] == 8
    assert body["object_name"].startswith("uploads/")
