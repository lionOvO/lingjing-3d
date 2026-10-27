import base64

import httpx
import pytest

from app import ImagePreparationError, _prepare_image_url


@pytest.mark.asyncio
async def test_internal_minio_image_becomes_data_uri(monkeypatch):
    monkeypatch.setenv("QWEN2VL_INTERNAL_IMAGE_HOSTS", "minio")
    payload = b"test-image-bytes"

    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("http://minio:9000/digital-human/uploads/")
        return httpx.Response(200, headers={"content-type": "image/webp"}, content=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _prepare_image_url("http://minio:9000/digital-human/uploads/avatar.webp?signature=private", client)

    assert result == "data:image/webp;base64," + base64.b64encode(payload).decode("ascii")


@pytest.mark.asyncio
async def test_external_image_url_is_rejected(monkeypatch):
    monkeypatch.setenv("QWEN2VL_INTERNAL_IMAGE_HOSTS", "minio")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as client:
        with pytest.raises(ImagePreparationError, match="受信任"):
            await _prepare_image_url("https://example.com/image.png", client)


@pytest.mark.asyncio
async def test_oversized_or_non_image_response_is_rejected(monkeypatch):
    monkeypatch.setenv("QWEN2VL_INTERNAL_IMAGE_HOSTS", "minio")
    monkeypatch.setenv("QWEN2VL_INTERNAL_IMAGE_MAX_MB", "1")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"not an image")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ImagePreparationError, match="格式"):
            await _prepare_image_url("http://minio:9000/digital-human/uploads/avatar.png", client)


@pytest.mark.asyncio
async def test_oversized_internal_image_is_rejected_before_reading(monkeypatch):
    monkeypatch.setenv("QWEN2VL_INTERNAL_IMAGE_HOSTS", "minio")
    monkeypatch.setenv("QWEN2VL_INTERNAL_IMAGE_MAX_MB", "1")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "image/png", "content-length": str(2 * 1024 * 1024)})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ImagePreparationError, match="超过"):
            await _prepare_image_url("http://minio:9000/digital-human/uploads/large.png", client)


def test_provider_prose_fields_are_validated_for_normalization():
    from app import AnalyzeResponse

    result = AnalyzeResponse.model_validate({
        "hair": "浅色短发",
        "face": "鹅蛋脸",
        "outfit": "圆领上衣",
        "style_tags": ["3D", "stylized"],
    })

    assert result.hair == "浅色短发"
    assert result.outfit == "圆领上衣"
