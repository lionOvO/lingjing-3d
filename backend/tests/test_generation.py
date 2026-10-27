import httpx
import pytest
from pydantic import ValidationError

from app.generation import (
    EngineName,
    GenerationEngineClient,
    GenerationRequest,
    GenerationResponseError,
    GenerationServiceUnavailable,
    build_generation_request,
    select_engine,
)


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://engine/generate")
            response = httpx.Response(self.status_code, request=request, json=self.payload)
            raise httpx.HTTPStatusError("engine error", request=request, response=response)

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, responses):
        self.responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json):
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_engine_client_retries_transient_failure():
    responses = [
        FakeResponse({"status": "error", "engine": "trellis2", "message": "busy"}, status_code=503),
        FakeResponse({"status": "completed", "engine": "trellis-2", "model_url": "mock://model.glb", "texture_urls": ["mock://a.png"]}),
    ]

    def factory(**kwargs):
        return FakeClient(responses)

    client = GenerationEngineClient(EngineName.TRELLIS2, base_url="http://engine", retries=1, backoff=0, client_factory=factory)
    result = await client.generate(GenerationRequest(task_id="1", source_image_url="upload://source.png"))
    assert result.model_url == "mock://model.glb"
    assert result.engine == EngineName.TRELLIS2


@pytest.mark.asyncio
async def test_engine_client_raises_after_retries():
    def factory(**kwargs):
        return FakeClient([FakeResponse({}, status_code=503)])

    client = GenerationEngineClient(EngineName.TRIPOSR, base_url="http://engine", retries=0, backoff=0, client_factory=factory)
    with pytest.raises(GenerationServiceUnavailable):
        await client.generate(GenerationRequest(task_id="1", source_image_url="upload://source.png"))


@pytest.mark.asyncio
async def test_node_error_is_visible_without_resubmitting_gpu_job():
    responses = [FakeResponse({"detail": "ComfyUI execution failed: CUDA out of memory"}, status_code=502)]
    client = GenerationEngineClient(EngineName.TRELLIS2, retries=3, backoff=0,
                                    client_factory=lambda **kwargs: FakeClient(responses))
    with pytest.raises(GenerationResponseError, match="CUDA out of memory"):
        await client.generate(GenerationRequest(task_id="1", source_image_url="upload://source.png"))
    assert responses == []


def test_generation_request_validates_output_format():
    with pytest.raises(ValidationError):
        GenerationRequest(source_image_url="upload://source.png", output_format="dae")


def test_quick_preview_selects_triposr():
    state = {"task_type": "anime_character", "generation_mode": "quick_preview", "source_image_url": "upload://source.png"}
    assert select_engine(state) == EngineName.TRIPOSR
    request = build_generation_request(state)
    assert request.engine == EngineName.TRIPOSR
    assert request.mode.value == "quick_preview"


def test_fast_mode_selects_triposr():
    state = {"task_type": "anime_character", "generation_mode": "fast", "source_image_url": "upload://source.png"}
    assert select_engine(state) == EngineName.TRIPOSR
    request = build_generation_request(state)
    assert request.engine == EngineName.TRIPOSR
    assert request.mode.value == "fast"


def test_balanced_mode_selects_triposr_with_balanced_preset():
    state = {"task_type": "anime_character", "generation_mode": "balanced", "source_image_url": "upload://source.png"}
    assert select_engine(state) == EngineName.TRIPOSR
    request = build_generation_request(state)
    assert request.engine == EngineName.TRIPOSR
    assert request.mode.value == "balanced"
    assert request.output_format == "glb"
    assert request.texture_resolution == "1024"
    assert request.mesh_density == "medium"
    assert request.pbr_enabled is False


def test_high_quality_mode_selects_trellis2():
    state = {"task_type": "anime_character", "generation_mode": "high_quality", "source_image_url": "upload://source.png"}
    assert select_engine(state) == EngineName.TRELLIS2
    request = build_generation_request(state)
    assert request.engine == EngineName.TRELLIS2
    assert request.mode.value == "high_quality"
    assert request.texture_resolution == "1024"
    assert request.mesh_density == "medium"


def test_high_quality_honors_supported_local_trellis_overrides():
    state = {"task_type": "anime_character", "generation_mode": "high_quality", "source_image_url": "upload://source.png", "generation_params": {"texture_resolution": "2048", "mesh_density": "low", "pbr_enabled": False}}
    request = build_generation_request(state)
    assert request.engine == EngineName.TRELLIS2
    assert request.texture_resolution == "2048"
    assert request.mesh_density == "low"
    assert request.pbr_enabled is True


def test_engine_response_preserves_real_artifact_path():
    result = GenerationEngineClient._parse_response({
        "status": "completed",
        "engine": "trellis2",
        "model_url": "artifact://abc123",
        "artifact_path": "/artifacts/abc123.glb",
        "metadata": {"real_inference": True},
    })
    assert result.model_url == "artifact://abc123"
    assert result.artifact_path == "/artifacts/abc123.glb"
    assert result.metadata["real_inference"] is True
