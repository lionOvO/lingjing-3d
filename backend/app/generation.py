"""Async integration clients for TRELLIS-2 and TripoSR.

The engine service is intentionally treated as an external boundary. Requests
and responses are validated with Pydantic so malformed adapter responses fail
with a useful, persisted task error instead of corrupting workflow state.
"""
from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import settings

logger = logging.getLogger("digital_human.generation")


class GenerationServiceError(RuntimeError):
    """Base error raised for an engine integration failure."""


class GenerationServiceUnavailable(GenerationServiceError):
    """Raised when an engine cannot be reached after retries."""


class GenerationResponseError(GenerationServiceError):
    """Raised when an engine returns an invalid or failed response."""


class EngineName(str, Enum):
    TRELLIS2 = "trellis2"
    TRIPOSR = "triposr"


class GenerationMode(str, Enum):
    """User-facing generation tiers.

    ``QUICK_PREVIEW`` is kept as a separate legacy value so tasks created by
    earlier frontend versions remain readable and preserve their persisted
    metadata. New requests should use ``FAST``.
    """

    FAST = "fast"
    BALANCED = "balanced"
    HIGH_QUALITY = "high_quality"
    QUICK_PREVIEW = "quick_preview"


# Effective settings for the three user-facing tiers.  The local TripoSR
# runner serves the preview tiers; high quality uses the configured adapter,
# including the verified local Pixal3D workflow. Keeping these values here prevents the UI,
# workflow and engine adapter from silently disagreeing.
TIER_PRESETS: dict[GenerationMode, dict[str, Any]] = {
    GenerationMode.FAST: {
        "engine": EngineName.TRIPOSR,
        "output_format": "glb",
        "texture_resolution": "512",
        "mesh_density": "low",
        "pbr_enabled": False,
    },
    GenerationMode.QUICK_PREVIEW: {
        "engine": EngineName.TRIPOSR,
        "output_format": "glb",
        "texture_resolution": "512",
        "mesh_density": "low",
        "pbr_enabled": False,
    },
    GenerationMode.BALANCED: {
        "engine": EngineName.TRIPOSR,
        "output_format": "glb",
        "texture_resolution": "1024",
        "mesh_density": "medium",
        "pbr_enabled": False,
    },
    GenerationMode.HIGH_QUALITY: {
        "engine": EngineName.TRELLIS2,
        "output_format": "glb",
        # Limit the default export atlas memory on the 6 GB GPU. This size
        # is independent of Pixal3D's internal 1024 cascade model stages.
        # A 2048px atlas remains an explicit advanced choice.
        "texture_resolution": "1024",
        "mesh_density": "medium",
        "pbr_enabled": True,
    },
}


class GenerationRequest(BaseModel):
    """Canonical request sent to a 3D engine adapter."""

    model_config = ConfigDict(extra="allow")

    task_id: str | None = None
    task_type: str = Field(default="anime_character", min_length=1, max_length=50)
    source_image_url: str = Field(min_length=1, max_length=2000)
    output_format: str = Field(default="glb", min_length=2, max_length=10)
    engine: EngineName = EngineName.TRELLIS2
    mode: GenerationMode = GenerationMode.HIGH_QUALITY
    texture_resolution: str = Field(default="2048", min_length=2, max_length=20)
    mesh_density: str = Field(default="medium", min_length=1, max_length=20)
    pbr_enabled: bool = True
    character_params: dict[str, Any] | None = None
    generation_params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, value: str) -> str:
        allowed = {"glb", "obj", "ply", "fbx", "stl"}
        normalized = value.lower().lstrip(".")
        if normalized not in allowed:
            raise ValueError(f"output_format must be one of {sorted(allowed)}")
        return normalized


class GenerationArtifact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model_url: str = Field(min_length=1, max_length=2000)
    artifact_path: str | None = Field(default=None, max_length=2000)
    texture_urls: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str = Field(min_length=1, max_length=30)
    engine: EngineName
    job_id: str | None = None
    artifact: GenerationArtifact | None = None
    artifacts: list[GenerationArtifact] = Field(default_factory=list)
    message: str | None = None

    @property
    def model_url(self) -> str | None:
        if self.artifact:
            return self.artifact.model_url
        if self.artifacts:
            return self.artifacts[0].model_url
        return None

    @property
    def texture_urls(self) -> list[str]:
        if self.artifact:
            return self.artifact.texture_urls
        return self.artifacts[0].texture_urls if self.artifacts else []

    @property
    def metadata(self) -> dict[str, Any]:
        if self.artifact:
            return self.artifact.metadata
        return self.artifacts[0].metadata if self.artifacts else {}

    @property
    def artifact_path(self) -> str | None:
        if self.artifact and self.artifact.artifact_path:
            return self.artifact.artifact_path
        return self.artifacts[0].artifact_path if self.artifacts else None


class GenerationEngineClient:
    """Retrying async HTTP client shared by the engine adapters."""

    def __init__(self, engine: EngineName, base_url: str | None = None, *, timeout: float | None = None, retries: int | None = None, backoff: float | None = None, client_factory: Any | None = None):
        self.engine = engine
        self.base_url = (base_url or settings.trellis_url).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.generation_http_timeout
        self.retries = max(0, retries if retries is not None else settings.generation_service_retries)
        self.backoff = max(0.0, backoff if backoff is not None else settings.generation_retry_backoff)
        self.client_factory = client_factory

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        request = request.model_copy(update={"engine": self.engine})
        payload = self._payload(request)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                client_factory = self.client_factory or httpx.AsyncClient
                async with client_factory(timeout=self.timeout) as client:
                    response = await client.post(f"{self.base_url}/generate", json=payload)
                    response.raise_for_status()
                    result = self._parse_response(response.json())
                if result.status.lower() in {"failed", "error"}:
                    raise GenerationResponseError(result.message or "3D engine reported failure")
                logger.info("3D generation request accepted task_id=%s engine=%s status=%s", request.task_id, self.engine.value, result.status)
                return result
            except GenerationResponseError:
                raise
            except httpx.HTTPStatusError as exc:
                # An adapter can report a completed-but-failed inference as a
                # 502 with a node error. Preserve that detail and do not submit
                # another expensive GPU job as a network retry.
                try:
                    detail = exc.response.json().get("detail")
                except (ValueError, AttributeError):
                    detail = None
                if detail:
                    raise GenerationResponseError(str(detail)) from exc
                last_error = exc
                if attempt >= self.retries:
                    raise GenerationServiceUnavailable(f"{self.engine.value} service unavailable: {exc}") from exc
                if self.backoff > 0:
                    await asyncio.sleep(self.backoff * (2 ** attempt))
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError, ValueError, TypeError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    logger.exception("3D engine unavailable task_id=%s engine=%s", request.task_id, self.engine.value)
                    raise GenerationServiceUnavailable(f"{self.engine.value} service unavailable: {exc}") from exc
                logger.warning("3D engine request retry task_id=%s engine=%s attempt=%s", request.task_id, self.engine.value, attempt + 1, exc_info=True)
                if self.backoff > 0:
                    await asyncio.sleep(self.backoff * (2 ** attempt))
            except Exception as exc:
                logger.exception("Unexpected 3D engine error task_id=%s engine=%s", request.task_id, self.engine.value)
                raise GenerationServiceError(str(exc)) from exc
        raise GenerationServiceUnavailable(f"{self.engine.value} service unavailable: {last_error}")

    async def generate_async(self, config: dict[str, Any]) -> dict[str, Any]:
        """Compatibility facade for the agent contract described in the spec."""
        request = GenerationRequest.model_validate({
            "task_id": config.get("task_id"),
            "task_type": config.get("task_type", "anime_character"),
            "source_image_url": config.get("input_image") or config.get("source_image_url"),
            "output_format": config.get("output_format", "glb"),
            "engine": self.engine,
            "mode": config.get("mode", "high_quality"),
            "texture_resolution": config.get("texture_resolution", "2048"),
            "mesh_density": config.get("mesh_density", "medium"),
            "pbr_enabled": config.get("pbr_enabled", True),
            "character_params": config.get("character_params"),
            "generation_params": config,
        })
        result = await self.generate(request)
        return {"status": result.status, "job_id": result.job_id, "model_url": result.model_url, "artifact_path": result.artifact_path, "texture_urls": result.texture_urls, "metadata": result.metadata}

    @staticmethod
    def _payload(request: GenerationRequest) -> dict[str, Any]:
        payload = request.model_dump(mode="json", exclude_none=True)
        params = payload.pop("generation_params", {})
        reserved = {"task_id", "task_type", "source_image_url", "input_image", "engine", "mode", "output_format", "character_params"}
        payload.update({key: value for key, value in params.items() if key not in reserved})
        payload["input_image"] = payload.pop("source_image_url")
        payload["output_format"] = request.output_format
        payload["engine"] = request.engine.value
        payload["mode"] = request.mode.value
        return payload

    @staticmethod
    def _parse_response(raw: Any) -> GenerationResult:
        if not isinstance(raw, dict):
            raise GenerationResponseError("3D engine returned a non-object response")
        engine_value = raw.get("engine", EngineName.TRELLIS2.value)
        try:
            engine = EngineName(str(engine_value).lower().replace("-", ""))
        except ValueError:
            engine = EngineName.TRELLIS2
        artifact_rows = raw.get("artifacts") or []
        response_texture_urls = _string_list(raw.get("texture_urls"))
        if isinstance(artifact_rows, dict):
            artifact_rows = [artifact_rows]
        artifacts: list[GenerationArtifact] = []
        for item in artifact_rows:
            if isinstance(item, str):
                artifacts.append(GenerationArtifact(model_url=item))
            elif isinstance(item, dict):
                model_url = item.get("model_url") or item.get("url")
                if model_url:
                    artifacts.append(GenerationArtifact(model_url=str(model_url), artifact_path=item.get("artifact_path"), texture_urls=_string_list(item.get("texture_urls")) or response_texture_urls, metadata=item.get("metadata") or {}))
        direct_url = raw.get("model_url")
        direct = GenerationArtifact(model_url=str(direct_url), artifact_path=raw.get("artifact_path"), texture_urls=response_texture_urls, metadata=raw.get("metadata") or {}) if direct_url else None
        return GenerationResult(status=str(raw.get("status", "completed")), engine=engine, job_id=raw.get("job_id") or raw.get("id"), artifact=direct, artifacts=artifacts, message=raw.get("message"))


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [str(value)]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


class Trellis2Service(GenerationEngineClient):
    def __init__(self, **kwargs: Any):
        super().__init__(EngineName.TRELLIS2, **kwargs)


class TripoSRService(GenerationEngineClient):
    def __init__(self, **kwargs: Any):
        super().__init__(EngineName.TRIPOSR, **kwargs)


def select_engine(state: dict[str, Any]) -> EngineName:
    """Choose the actual engine behind each user-facing generation tier."""
    params = state.get("generation_params") or {}
    mode = str(state.get("generation_mode") or params.get("mode") or params.get("generation_mode") or "high_quality").lower().replace("-", "_")
    if mode in {
        GenerationMode.FAST.value,
        GenerationMode.QUICK_PREVIEW.value,
        GenerationMode.BALANCED.value,
        "preview",
        "quick",
        "standard",
    }:
        return EngineName.TRIPOSR
    return EngineName.TRELLIS2


def build_generation_request(state: dict[str, Any], engine: EngineName | None = None) -> GenerationRequest:
    params = dict(state.get("generation_params") or {})
    selected = engine or select_engine(state)
    mode = GenerationMode.QUICK_PREVIEW if selected == EngineName.TRIPOSR else GenerationMode.HIGH_QUALITY
    raw_mode = str(state.get("generation_mode") or params.get("mode") or params.get("generation_mode") or "").lower().replace("-", "_")
    if raw_mode in {GenerationMode.FAST.value}:
        mode = GenerationMode.FAST
    elif raw_mode in {GenerationMode.QUICK_PREVIEW.value, "preview", "quick"}:
        mode = GenerationMode.QUICK_PREVIEW
    elif raw_mode in {GenerationMode.BALANCED.value, "standard"}:
        mode = GenerationMode.BALANCED
    elif raw_mode in {GenerationMode.HIGH_QUALITY.value, "quality", "high"}:
        mode = GenerationMode.HIGH_QUALITY
    preset = TIER_PRESETS[mode]
    selected = preset["engine"]
    requested_texture = str(params.get("texture_resolution", preset["texture_resolution"]))
    requested_density = str(params.get("mesh_density", preset["mesh_density"]))
    # High-quality local Trellis2 exposes only the values its 6 GB workflow
    # can interpret safely. Other tiers retain their fixed presets.
    effective_texture = requested_texture if mode == GenerationMode.HIGH_QUALITY and requested_texture in {"1024", "2048"} else preset["texture_resolution"]
    effective_density = requested_density if requested_density in {"low", "medium", "high"} else preset["mesh_density"]
    # The local high-quality graph always generates and exports PBR material.
    effective_pbr = preset["pbr_enabled"]
    params.update({
        "engine": selected.value,
        "generation_mode": mode.value,
        "texture_resolution": effective_texture,
        "mesh_density": effective_density,
        "pbr_enabled": effective_pbr,
    })
    return GenerationRequest(task_id=str(state.get("task_id")) if state.get("task_id") is not None else None, task_type=str(state.get("task_type", "anime_character")), source_image_url=str(state.get("source_image_url", "")), output_format=str(preset["output_format"]), engine=selected, mode=mode, texture_resolution=str(effective_texture), mesh_density=str(effective_density), pbr_enabled=effective_pbr, character_params=state.get("character_features"), generation_params=params)


async def generate_model(state: dict[str, Any]) -> GenerationResult:
    engine = select_engine(state)
    service = Trellis2Service() if engine == EngineName.TRELLIS2 else TripoSRService()
    return await service.generate(build_generation_request(state, engine))
