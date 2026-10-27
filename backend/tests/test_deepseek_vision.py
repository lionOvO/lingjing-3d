import base64
import io
import json

import httpx
import pytest
from fastapi import HTTPException
from PIL import Image
from pydantic import SecretStr

from app import deepseek_vision as vision
from app.security import create_access_token
from tests.test_studio import seed

real_post = httpx.AsyncClient.post


def png():
    image = Image.new("RGBA", (200, 400), (255, 0, 0, 0))
    image.putpixel((100, 200), (200, 50, 50, 255))
    buf = io.BytesIO(); image.save(buf, "PNG")
    return buf.getvalue()


def advice():
    return {"subject_type": "building", "description": "完整楼阁", "bounds": {"x": 5, "y": 8, "right": 95, "bottom": 95},
            "keep_parts": ["底座", "柱子"], "exclude_parts": ["工具栏"], "warnings": [], "confidence": .92}


def review():
    return {"verdict": "pass", "missing_parts": [], "background_residue": [], "explanation": "结构完整", "confidence": .95}


def provider(monkeypatch, result, *, status=200, finish="stop"):
    monkeypatch.setattr(vision.settings, "deepseek_api_key", SecretStr("test-only-key"))
    calls = []
    async def post(self, url, **kwargs):
        if str(url).startswith("/api/"):
            return await real_post(self, url, **kwargs)
        calls.append((url, kwargs))
        return httpx.Response(status, request=httpx.Request("POST", url), json={"choices": [{
            "message": {"content": json.dumps(result)}, "finish_reason": finish}]})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    return calls


def test_preview_composites_transparency_without_changing_aspect():
    url = vision.vision_image(png())
    image = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    assert image.size == (200, 400)
    assert all(abs(channel - 150) < 4 for channel in image.getpixel((0, 0)))
    with pytest.raises(HTTPException): vision.vision_image(b"not an image")


@pytest.mark.asyncio
async def test_building_routes_to_generic_segmentation_and_images_are_inline(monkeypatch):
    calls = provider(monkeypatch, advice())
    result = await vision.inspect_preparation(png())
    assert result["recommended_model"] == "u2net"
    url, args = calls[0]
    assert url == "https://api.deepseek.com/chat/completions"
    assert args["json"]["model"] == "deepseek-flash"
    assert args["json"]["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "test-only-key" not in json.dumps(result)


@pytest.mark.asyncio
async def test_anime_routes_to_anime_segmentation(monkeypatch):
    result = advice(); result["subject_type"] = "anime_character"
    provider(monkeypatch, result)
    assert (await vision.inspect_preparation(png()))["recommended_model"] == "isnet-anime"


@pytest.mark.asyncio
@pytest.mark.parametrize("missing,residue,confidence,expected", [([], [], .95, "pass"), (["底座"], [], .95, "fail"), ([], ["工具栏"], .95, "fail"), ([], [], .5, "uncertain")])
async def test_review_never_passes_known_missing_parts_or_low_confidence(monkeypatch, missing, residue, confidence, expected):
    result = review(); result.update(missing_parts=missing, background_residue=residue, confidence=confidence)
    calls = provider(monkeypatch, result)
    output = await vision.inspect_preparation(png(), png())
    assert output["verdict"] == expected
    assert output["candidate_sha256"]
    assert len(calls[0][1]["json"]["messages"][0]["content"]) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("result,finish", [({"description": "missing fields"}, "stop"), (advice(), "length"), ({**advice(), "bounds": {"x": 90, "right": 10, "y": 0, "bottom": 100}}, "stop")])
async def test_invalid_and_incomplete_responses_are_rejected(monkeypatch, result, finish):
    provider(monkeypatch, result, finish=finish)
    with pytest.raises(HTTPException) as exc: await vision.inspect_preparation(png())
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_missing_key_and_provider_failure_are_not_success(monkeypatch):
    monkeypatch.setattr(vision.settings, "deepseek_api_key", SecretStr(""))
    with pytest.raises(HTTPException) as exc: await vision.inspect_preparation(png())
    assert exc.value.status_code == 503
    provider(monkeypatch, {}, status=401)
    with pytest.raises(HTTPException, match="") as exc: await vision.inspect_preparation(png())
    assert exc.value.status_code == 502 and "密钥无效" in exc.value.detail


@pytest.mark.asyncio
async def test_authenticated_upload_endpoint_and_status_do_not_expose_credentials(client, db_session, monkeypatch):
    owner, *_ = await seed(db_session)
    headers = {"Authorization": f"Bearer {create_access_token(owner.id)}"}
    path = "/api/v1/studio/images/vision-preparation"
    assert (await client.post(path, files={"image": ("test.png", png(), "image/png")})).status_code == 401
    provider(monkeypatch, advice())
    status = await client.get("/api/v1/studio/images/vision-status", headers=headers)
    assert status.json() == {"configured": True, "model": "deepseek-flash"}
    response = await client.post(path, headers=headers, files={"image": ("test.png", png(), "image/png")})
    assert response.status_code == 200 and response.json()["recommended_model"] == "u2net"
    provider(monkeypatch, review())
    response = await client.post(path, headers=headers, files={"image": ("test.png", png(), "image/png"), "candidate": ("out.png", png(), "image/png")})
    assert response.status_code == 200 and response.json()["verdict"] == "pass"
