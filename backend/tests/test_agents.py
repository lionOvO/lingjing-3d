from unittest.mock import patch

import pytest

from app.agents import CharacterAnalysisAgent, CharacterNormalizationAgent, ModelGenerationAgent, QualityCheckAgent, QualityRepairRAGAgent, RAGRetrievalAgent, RetrievalRerankAgent, DeterministicQualityCheckAgent, workflow
from app.config import settings
import httpx


@pytest.mark.asyncio
@pytest.mark.parametrize("required", [True, False])
async def test_unavailable_analysis_is_explicit_and_only_optional_when_configured(monkeypatch, required):
    class OfflineClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): raise httpx.ConnectError("offline")
    monkeypatch.setattr(settings, "vision_analysis_required", required)
    with patch("app.agents.httpx.AsyncClient", return_value=OfflineClient()):
        state = await CharacterAnalysisAgent().run({"task_id": "1", "source_image_url": "upload://a.png", "generation_params": {"generation_mode": "high_quality"}})
    if required:
        assert state["status"] == "failed"
    else:
        assert state["status"] == "analyzing"
        assert state["analysis_skipped"] is True
        assert state["character_features"]["source"] == "image-only"
        assert state["character_features"]["confidence"] == 0
        assert state["character_features"]["hair"]["color"] == "unknown"
        assert state["error_message"] is None


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

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
        return FakeResponse(self.responses[url.rsplit("/", 1)[-1]])


class FakeSearchClient:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = 0

    def search(self, **kwargs):
        self.calls += 1
        return self.rows


@pytest.mark.asyncio
async def test_character_analysis_normalizes_response():
    fake = FakeClient({"analyze": {"character_type": "anime_humanoid", "style_tags": ["moe"]}})
    with patch("app.agents.httpx.AsyncClient", return_value=fake):
        state = await CharacterAnalysisAgent().run({"task_id": "1", "source_image_url": "upload://a.png"})
    assert state["status"] == "analyzing"
    assert state["character_features"]["style_tags"] == ["moe"]


def test_character_normalization_supports_legacy_and_chinese_fields():
    features = CharacterNormalizationAgent.normalize({
        "character_type": "动漫人物",
        "gender": "女性",
        "hair_color": "银色",
        "hair_style": "长直发",
        "eye_color": "蓝色",
        "pose": "站立",
        "style_tags": "奇幻，柔光，奇幻",
        "confidence": 0.9,
    })
    assert features["character_type"] == "anime_humanoid"
    assert features["gender"] == "female"
    assert features["hair"] == {"color": "silver", "style": "long_straight", "length": "unknown"}
    assert features["style_tags"] == ["奇幻", "柔光"]
    assert "outfit" in features


def test_character_normalization_marks_unknown_and_low_confidence_fields():
    features = CharacterNormalizationAgent.normalize({"confidence": 0.2})
    assert features["uncertain_fields"]
    assert "hair" in features["uncertain_fields"]


@pytest.mark.asyncio
async def test_rag_rerank_exposes_sources_and_confidence():
    state = await RetrievalRerankAgent().run({
        "task_id": "1",
        "character_features": {},
        "retrieved_context": [
            {"collection": "generation_params_collection", "score": 0.4, "success_rate": 0.95, "best_params": '{"steps": 30}'},
            {"collection": "character_style_collection", "score": 0.8, "success_rate": 0.5, "generation_params": '{"steps": 60}'},
        ],
        "generation_params": {},
    })
    assert state["retrieved_context"][0]["score"] == 0.8
    assert state["retrieval_sources"][0]["collection"] == "character_style_collection"
    assert state["retrieval_confidence"] == 0.8
    assert state["generation_params"]["steps"] == 30 or state["generation_params"]["steps"] == 60


@pytest.mark.asyncio
async def test_rag_fallback_without_milvus():
    state = await RAGRetrievalAgent(client=object()).run({"task_id": "1", "character_features": {}})
    assert state["status"] == "retrieving"
    assert state["retrieved_context"] == []
    assert state["generation_params"]["pbr_enabled"] is True


@pytest.mark.asyncio
async def test_model_generation_parses_artifacts():
    fake = FakeClient({"generate": {"engine": "trellis-2", "artifacts": [{"model_url": "https://cdn/model.glb"}], "texture_urls": ["https://cdn/albedo.png"]}})
    with patch("app.generation.httpx.AsyncClient", return_value=fake):
        state = await ModelGenerationAgent().run({"task_id": "1", "task_type": "anime_character", "source_image_url": "upload://a.png", "generation_params": {}})
    assert state["generated_model_url"] == "https://cdn/model.glb"
    assert state["generated_textures"] == ["https://cdn/albedo.png"]


@pytest.mark.asyncio
async def test_model_generation_persists_generating_stage_before_request():
    fake = FakeClient({"generate": {"engine": "trellis2", "model_url": "https://cdn/model.glb"}})
    stages = []

    async def persist(status):
        stages.append(status)

    with patch("app.generation.httpx.AsyncClient", return_value=fake):
        state = await ModelGenerationAgent().run({
            "task_id": "1",
            "task_type": "anime_character",
            "source_image_url": "upload://a.png",
            "generation_params": {},
            "status_callback": persist,
        })
    assert state["status"] == "generating"
    assert stages == ["generating"]


@pytest.mark.asyncio
async def test_quality_accepts_renderable_non_watertight_mesh():
    agent = QualityCheckAgent()
    state = {"task_id": "1", "retry_count": 0, "generation_params": {"mode": "quick_preview"}, "generation_metadata": {"watertight": False, "manifold": False}}
    state = await agent.run(state)
    assert state["quality_score"] == pytest.approx(0.6)
    assert state["evaluation_result"] == "pass"
    assert state["generation_metadata"]["quality_mode"] == "quick_preview"
    assert "watertight check failed" in state["generation_metadata"]["quality_warnings"]


@pytest.mark.asyncio
async def test_fast_mode_accepts_non_watertight_mesh():
    state = {
        "task_id": "1",
        "retry_count": 0,
        "generation_params": {"mode": "fast"},
        "generation_metadata": {"watertight": False, "manifold": False, "face_count": 1000},
    }
    state = await QualityCheckAgent().run(state)
    assert state["evaluation_result"] == "pass"
    assert state["generation_metadata"]["quality_mode"] == "fast"


@pytest.mark.asyncio
async def test_balanced_mode_requires_manifold_but_not_watertight():
    agent = QualityCheckAgent()
    state = {
        "task_id": "1",
        "retry_count": 0,
        "generation_params": {"mode": "balanced"},
        "generation_metadata": {"watertight": False, "manifold": True, "face_count": 1000},
    }
    state = await agent.run(state)
    assert state["evaluation_result"] == "pass"
    assert state["generation_metadata"]["quality_mode"] == "balanced"


@pytest.mark.asyncio
async def test_balanced_mode_delivers_non_manifold_mesh_with_warning():
    state = {
        "task_id": "1",
        "retry_count": 0,
        "generation_params": {"mode": "balanced"},
        "generation_metadata": {"watertight": True, "manifold": False, "face_count": 1000},
    }
    state = await QualityCheckAgent().run(state)
    assert state["evaluation_result"] == "pass"
    assert state["retry_count"] == 0
    assert "manifold check failed" in state["generation_metadata"]["quality_warnings"]


@pytest.mark.asyncio
async def test_high_quality_requires_watertight_and_manifold():
    agent = QualityCheckAgent()
    state = {
        "task_id": "1",
        "retry_count": 0,
        "generation_params": {"mode": "high_quality"},
        "generation_metadata": {"watertight": False, "manifold": False, "face_count": 1000},
    }
    state = await agent.run(state)
    assert state["evaluation_result"] == "retry"
    assert state["retry_count"] == 1


@pytest.mark.asyncio
async def test_high_quality_does_not_assume_missing_topology_metadata_passes():
    agent = QualityCheckAgent()
    state = {
        "task_id": "1",
        "retry_count": 3,
        "generation_params": {"mode": "high_quality"},
        "generation_metadata": {"face_count": 1000, "texture_resolution": "2048"},
    }
    state = await agent.run(state)
    assert state["evaluation_result"] == "fail"
    assert state["status"] == "failed"


@pytest.mark.asyncio
async def test_local_comfyui_high_quality_delivers_topology_warnings():
    state = {
        "task_id": "local-1",
        "retry_count": 0,
        "generation_params": {"mode": "high_quality", "provider": "local_comfyui"},
        "generation_metadata": {"provider": "local_comfyui", "watertight": False, "manifold": False, "face_count": 506264, "texture_resolution": "1024", "degenerate_faces": 0},
    }
    state = await QualityCheckAgent().run(state)
    assert state["evaluation_result"] == "pass"
    assert "watertight check failed" in state["generation_metadata"]["quality_warnings"]


@pytest.mark.asyncio
async def test_triposr_engine_uses_preview_quality_policy_for_legacy_state():
    agent = QualityCheckAgent()
    state = {
        "task_id": "1",
        "retry_count": 0,
        "generation_params": {"engine": "triposr"},
        "generation_metadata": {"engine": "triposr", "watertight": False, "manifold": False},
    }
    state = await agent.run(state)
    assert state["evaluation_result"] == "pass"
    assert state["generation_metadata"]["quality_mode"] == "quick_preview"


@pytest.mark.asyncio
async def test_quality_retry_then_failure_for_fixable_mesh_problem():
    agent = QualityCheckAgent()
    state = {
        "task_id": "1",
        "retry_count": 0,
        "generation_params": {"texture_resolution": "256"},
        "generation_metadata": {"watertight": False, "manifold": False, "face_count": 10},
    }
    state = await agent.run(state)
    assert state["evaluation_result"] == "retry"
    assert state["retry_count"] == 1
    state["retry_count"] = 3
    state = await agent.run(state)
    assert state["evaluation_result"] == "fail"
    assert state["status"] == "failed"


@pytest.mark.asyncio
async def test_quality_repair_rag_only_runs_after_failed_deterministic_check():
    client = FakeSearchClient([[{"id": "case-1", "score": 0.91, "quality_repair": {"mesh_density": "high"}}]])
    state = await DeterministicQualityCheckAgent().run({
        "task_id": "1", "generation_params": {"mode": "high_quality"},
        "generation_metadata": {"face_count": 1000, "watertight": False, "manifold": True, "texture_resolution": "2048"},
    })
    assert any(not passed for passed in state["quality_checks"].values())
    state = await QualityRepairRAGAgent(client=client).run(state)
    assert client.calls == 1
    assert state["quality_repair_suggestions"][0]["suggestion"]["mesh_density"] == "high"


@pytest.mark.asyncio
async def test_quality_repair_rag_is_skipped_when_checks_pass():
    client = FakeSearchClient()
    state = {"quality_checks": {"watertight": True, "manifold": True, "face_count_ok": True}}
    state = await QualityRepairRAGAgent(client=client).run(state)
    assert client.calls == 0
    assert state["quality_repair_suggestions"] == []


@pytest.mark.asyncio
async def test_workflow_generation_failure_is_terminal():
    state = await workflow.ainvoke({"task_id": "1", "task_type": "anime_character", "source_image_url": "", "generation_params": {}})
    assert state["status"] == "failed"
    assert state["error_message"]


def test_worker_requeues_inflight_generation_when_worker_is_lost():
    """Long GPU jobs must not be acknowledged before their workflow ends."""
    from app.worker import celery_app

    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_worker_does_not_reuse_aiomysql_connections_across_event_loops():
    from sqlalchemy.pool import NullPool

    from app.worker import _worker_engine_options

    assert _worker_engine_options()["poolclass"] is NullPool
