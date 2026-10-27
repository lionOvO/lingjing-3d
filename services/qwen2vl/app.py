"""Configurable vision-analysis adapter without fabricated fallbacks."""
from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("qwen2vl.adapter")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
app = FastAPI(title="Qwen2-VL adapter", version="1.0.0")

SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


class ImagePreparationError(ValueError):
    """Raised when a supplied image cannot be safely sent to the provider."""


class AnalyzeRequest(BaseModel):
    image_url: str = Field(min_length=1, max_length=4000)
    prompt: str = Field(default="Extract character attributes as strict JSON.", max_length=12000)


class AnalyzeResponse(BaseModel):
    model_config = {"extra": "allow"}
    character_type: str = "unknown"
    gender: str = "unknown"
    # Providers may return prose here. The normalization agent handles both
    # forms before persisting the canonical structured representation.
    hair: dict[str, Any] | str = {}
    face: dict[str, Any] | str = {}
    outfit: dict[str, Any] | str = {}
    pose: str = "unknown"
    style_tags: list[str] = []
    confidence: float = Field(default=0.0, ge=0, le=1)
    source: str = "qwen2-vl"


def _provider_url() -> str | None:
    value = os.getenv("QWEN2VL_PROVIDER_URL") or os.getenv("QWEN2VL_API_URL") or os.getenv("ARK_API_URL")
    if value and not value.rstrip("/").endswith("/chat/completions"):
        value = value.rstrip("/") + "/chat/completions"
    return value


def _model_name() -> str:
    return os.getenv("QWEN2VL_MODEL") or os.getenv("ARK_API_MODEL") or "qwen-vl-max"


def _api_key() -> str | None:
    return os.getenv("QWEN2VL_API_KEY") or os.getenv("ARK_API_KEY")


def _internal_image_hosts() -> set[str]:
    """Return explicitly trusted object-storage hostnames.

    Source uploads are stored behind Docker's private ``minio`` hostname.
    Keeping this an allow-list prevents the adapter from becoming an arbitrary
    network fetcher when it converts an image URL into provider-ready bytes.
    """
    configured = os.getenv("QWEN2VL_INTERNAL_IMAGE_HOSTS", "minio")
    return {host.strip().lower() for host in configured.split(",") if host.strip()}


def _max_image_bytes() -> int:
    try:
        megabytes = float(os.getenv("QWEN2VL_INTERNAL_IMAGE_MAX_MB", "10"))
    except ValueError:
        megabytes = 10
    return int(max(1, min(megabytes, 50)) * 1024 * 1024)


def _is_data_image_uri(value: str) -> bool:
    header, separator, encoded = value.partition(",")
    return bool(
        separator
        and encoded
        and header.startswith("data:")
        and ";base64" in header.lower()
        and header[5:].split(";", 1)[0].lower() in SUPPORTED_IMAGE_TYPES
    )


async def _prepare_image_url(image_url: str, client: httpx.AsyncClient) -> str:
    """Turn a trusted internal image into a data URI for cloud providers.

    Cloud models cannot resolve Docker-only hostnames such as ``minio``. The
    image must therefore be read inside this network and passed as bytes. No
    arbitrary URL is fetched here: only configured internal hostnames qualify.
    """
    if _is_data_image_uri(image_url):
        return image_url

    parsed = urlparse(image_url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or hostname not in _internal_image_hosts():
        raise ImagePreparationError("图片地址不是受信任的内部对象存储地址")

    max_bytes = _max_image_bytes()
    try:
        async with client.stream("GET", image_url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower().strip()
            if content_type not in SUPPORTED_IMAGE_TYPES:
                raise ImagePreparationError("上传图片格式不受支持，仅支持 PNG、JPG/JPEG 或 WEBP")
            try:
                declared_size = int(response.headers.get("content-length", "0") or 0)
            except ValueError:
                declared_size = 0
            if declared_size > max_bytes:
                raise ImagePreparationError(f"上传图片超过 {int(max_bytes / 1024 / 1024)}MB 限制")

            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > max_bytes:
                    raise ImagePreparationError(f"上传图片超过 {int(max_bytes / 1024 / 1024)}MB 限制")
            content = bytes(chunks)
    except ImagePreparationError:
        raise
    except httpx.HTTPError as exc:
        raise ImagePreparationError("无法从对象存储读取上传图片") from exc

    if not content:
        raise ImagePreparationError("上传图片为空")
    logger.info("Prepared internal image for vision provider host=%s bytes=%s type=%s", hostname, len(content), content_type)
    return f"data:{content_type};base64,{base64.b64encode(content).decode('ascii')}"


def _provider_error_detail(exc: httpx.HTTPStatusError) -> str:
    """Produce a short user-safe message without logging credentials or payloads."""
    response = exc.response
    body = response.text.strip().replace("\n", " ")[:300]
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error", payload)
            if isinstance(error, dict):
                body = str(error.get("message") or error.get("code") or body)
    except (ValueError, json.JSONDecodeError):
        pass
    suffix = f"：{body}" if body else ""
    return f"视觉模型服务拒绝该请求（HTTP {response.status_code}）{suffix}"


def _extract_json(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and "choices" not in payload:
        return payload
    try:
        content = payload["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if not isinstance(content, str):
            raise ValueError("message content is not text")
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:]
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("vision provider returned invalid JSON content") from exc
    raise ValueError("vision provider returned a non-object response")


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"status": "ok", "model": _model_name(), "provider_configured": bool(_provider_url())}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(payload: AnalyzeRequest) -> dict[str, Any]:
    provider = _provider_url()
    if not provider:
        raise HTTPException(status_code=503, detail="未配置真实视觉模型服务，请设置 QWEN2VL_PROVIDER_URL")
    headers = {"Content-Type": "application/json"}
    api_key = _api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        # Do not inherit proxy environment variables for Docker's internal
        # MinIO request; the cloud-provider request retains normal proxy use.
        async with httpx.AsyncClient(
            timeout=float(os.getenv("QWEN2VL_INTERNAL_IMAGE_TIMEOUT", "30")),
            trust_env=False,
            follow_redirects=False,
        ) as image_client:
            image_reference = await _prepare_image_url(payload.image_url, image_client)
        body = {"model": _model_name(), "temperature": 0, "response_format": {"type": "json_object"}, "messages": [{"role": "user", "content": [{"type": "text", "text": payload.prompt}, {"type": "image_url", "image_url": {"url": image_reference}}]}]}
        async with httpx.AsyncClient(timeout=float(os.getenv("QWEN2VL_TIMEOUT", "120"))) as client:
            response = await client.post(provider, headers=headers, json=body)
            response.raise_for_status()
            result = _extract_json(response.json())
        result.setdefault("source", f"qwen2-vl:{_model_name()}")
        return result
    except ImagePreparationError as exc:
        logger.warning("Vision image preparation rejected: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        detail = _provider_error_detail(exc)
        logger.warning("Vision provider returned HTTP %s: %s", exc.response.status_code, detail)
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        logger.exception("Vision provider request failed")
        raise HTTPException(status_code=502, detail=f"视觉模型服务请求失败: {exc}") from exc
    except (TypeError, ValueError) as exc:
        logger.exception("Vision provider response invalid")
        raise HTTPException(status_code=502, detail=f"视觉模型返回格式无效: {exc}") from exc
