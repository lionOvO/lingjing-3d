"""Async LangGraph workflow for image-to-3D generation."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, TypedDict

import httpx
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph
from .schemas import NormalizedCharacterFeatures

from .config import settings
from .generation import (
    EngineName,
    GenerationEngineClient,
    GenerationMode,
    GenerationServiceError,
    build_generation_request,
    select_engine,
    Trellis2Service,
    TripoSRService,
)

logger = logging.getLogger("digital_human.agents")


def deterministic_embedding(text: str, dim: int) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [digest[i % len(digest)] / 127.5 - 1.0 for i in range(dim)]


class GenerationState(TypedDict, total=False):
    task_id: str
    project_id: int
    task_type: str
    source_image_url: str
    output_format: str
    character_features: dict[str, Any] | None
    raw_character_analysis: dict[str, Any] | None
    analysis_skipped: bool
    retrieved_context: list[dict[str, Any]] | None
    retrieval_sources: list[dict[str, Any]] | None
    retrieval_confidence: float | None
    retrieval_degraded: bool
    retrieval_query: str | None
    generation_params: dict[str, Any] | None
    generation_mode: str | None
    generated_model_url: str | None
    generated_artifact_path: str | None
    generated_textures: list[str] | None
    generation_job_id: str | None
    generation_metadata: dict[str, Any] | None
    quality_score: float | None
    quality_checks: dict[str, bool] | None
    quality_repair_suggestions: list[dict[str, Any]] | None
    quality_repair_sources: list[dict[str, Any]] | None
    quality_repair_degraded: bool
    evaluation_result: str | None
    retry_count: int
    error_message: str | None
    status: str
    # Worker-only callback. LangGraph keeps this local value in state while
    # the Celery worker uses it to persist stage transitions immediately.
    status_callback: Any


async def _persist_status(state: GenerationState, status: str) -> None:
    callback = state.get("status_callback")
    if callback is None:
        return
    try:
        result = callback(status)
        if hasattr(result, "__await__"):
            await result
    except Exception:
        # Progress persistence must never break the actual generation flow.
        logger.warning("Unable to persist workflow status task_id=%s status=%s", state.get("task_id"), status, exc_info=True)


# Backward-compatible names used by the initial API scaffold.
WorkflowState = GenerationState


class CharacterAnalysisAgent:
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是专业的动漫角色分析专家，只返回严格 JSON。提取 character_type、gender、hair、face、outfit、pose、style_tags。"),
        ("human", "请分析图片：{image_url}"),
    ])

    def __init__(self, milvus_client: Any | None = None):
        self.milvus_client = milvus_client

    async def run(self, state: GenerationState) -> GenerationState:
        state["status"] = "analyzing"
        await _persist_status(state, "analyzing")
        image_url = state.get("source_image_url", "")
        if not image_url:
            state["error_message"] = "source_image_url is required"
            state["status"] = "failed"
            await _persist_status(state, "failed")
            logger.error("Character analysis missing image task_id=%s", state.get("task_id"))
            return state
        if (state.get("generation_params") or {}).get("vision_analysis") is False:
            # Confirmed image preparation replaces the optional language-analysis stage.
            raw={"source":"prepared-image","analysis_skipped":True,"warning":"已使用确认的参考图，不调用视觉语言模型。","confidence":0.0}
            state["analysis_skipped"]=True
            state["raw_character_analysis"]=raw
            state["character_features"]=self._normalize(raw)
            return state
        try:
            async with httpx.AsyncClient(timeout=settings.agent_http_timeout) as client:
                response = await client.post(f"{settings.qwen2vl_url.rstrip('/')}/analyze", json={"image_url": image_url, "prompt": self.prompt.format(image_url=image_url)})
                response.raise_for_status()
                data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Qwen2-VL returned a non-object response")
            state["raw_character_analysis"] = data
            # Keep this compatibility value for callers that invoke the
            # analysis agent directly. The graph runs the dedicated
            # normalization node immediately afterwards.
            state["character_features"] = self._normalize(data)
            logger.info("Character analysis completed task_id=%s", state.get("task_id"))
        except Exception as exc:
            mode = (state.get("generation_params") or {}).get("generation_mode", state.get("generation_mode"))
            if not settings.vision_analysis_required and mode == "high_quality":
                warning = "视觉分析服务不可用，本次未识别角色属性；直接使用参考图及所选参数生成 3D。"
                state["analysis_skipped"] = True
                state["raw_character_analysis"] = {"source": "image-only", "analysis_skipped": True, "warning": warning, "confidence": 0.0}
                state["character_features"] = self._normalize(state["raw_character_analysis"])
                state["error_message"] = None
                logger.warning("Optional character analysis unavailable task_id=%s; using source image directly", state.get("task_id"))
                return state
            state["error_message"] = f"Character analysis failed: {exc}"
            state["status"] = "failed"
            await _persist_status(state, "failed")
            logger.exception("Character analysis failed task_id=%s", state.get("task_id"))
        return state

    async def _save_to_milvus(self, features: dict[str, Any], image_url: str) -> None:
        if self.milvus_client is None:
            return
        try:
            tags = features.get("style_tags") or []
            row = {"style_embedding": deterministic_embedding(json.dumps(features, ensure_ascii=False), 1024), "style_name": features.get("character_type", "anime"), "tags": json.dumps(tags, ensure_ascii=False), "generation_params": "{}", "reference_image_url": image_url, "created_at": int(time.time())}
            await asyncio.to_thread(self.milvus_client.insert, collection_name="character_style_collection", data=[row])
        except Exception:
            logger.warning("Milvus feature insert failed image=%s", image_url, exc_info=True)

    @staticmethod
    def _normalize(data: dict[str, Any]) -> dict[str, Any]:
        """Compatibility wrapper around the canonical normalizer."""
        return CharacterNormalizationAgent.normalize(data)


class CharacterNormalizationAgent:
    """Convert provider output and legacy flat fields into a strict schema."""

    _MAPS = {
        "gender": {"女": "female", "女性": "female", "女生": "female", "男": "male", "男性": "male", "女生": "female", "未知": "unknown"},
        "character_type": {"二次元": "anime_humanoid", "动漫人物": "anime_humanoid", "人类": "human", "humanoid": "anime_humanoid"},
        "pose": {"站立": "standing", "站着": "standing", "坐姿": "sitting", "坐着": "sitting", "正面": "front", "侧面": "profile"},
    }
    _COLORS = {"银": "silver", "银色": "silver", "白": "white", "白色": "white", "黑": "black", "黑色": "black", "棕": "brown", "棕色": "brown", "红": "red", "红色": "red", "蓝": "blue", "蓝色": "blue", "金": "blonde", "金色": "blonde"}
    _HAIR_STYLES = {"长直发": "long_straight", "直发": "straight", "短发": "short", "双马尾": "twintails", "马尾": "ponytail", "卷发": "curly", "波浪": "wavy"}

    def __init__(self, milvus_client: Any | None = None):
        self.milvus_client = milvus_client

    async def run(self, state: GenerationState) -> GenerationState:
        state["status"] = "analyzing"
        await _persist_status(state, "analyzing")
        raw = state.get("raw_character_analysis") or state.get("character_features") or {}
        try:
            normalized = self.normalize(raw)
            state["character_features"] = normalized
            if not state.get("analysis_skipped"):
                await self._save_to_milvus(normalized, state.get("source_image_url", ""))
            logger.info("Character normalization completed task_id=%s uncertain=%s", state.get("task_id"), normalized.get("uncertain_fields", []))
        except Exception as exc:
            state["error_message"] = f"Character normalization failed: {exc}"
            state["status"] = "failed"
            await _persist_status(state, "failed")
            logger.exception("Character normalization failed task_id=%s", state.get("task_id"))
        return state

    @classmethod
    def normalize(cls, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("vision analysis must be an object")

        def text(value: Any, default: str = "unknown") -> str:
            if value is None:
                return default
            value = str(value).strip()
            return value or default

        def mapped(field: str, value: Any) -> str:
            value = text(value)
            return cls._MAPS.get(field, {}).get(value.lower(), cls._MAPS.get(field, {}).get(value, value.lower()))

        def nested(name: str) -> dict[str, Any]:
            value = data.get(name)
            return value if isinstance(value, dict) else {}

        hair = nested("hair")
        face = nested("face")
        outfit = nested("outfit")
        color = text(hair.get("color", data.get("hair_color")))
        color = cls._COLORS.get(color.lower(), cls._COLORS.get(color, color.lower()))
        style = text(hair.get("style", data.get("hair_style")))
        style = cls._HAIR_STYLES.get(style, cls._HAIR_STYLES.get(style.lower(), style.lower()))
        accessories = outfit.get("accessories", data.get("accessories", []))
        if isinstance(accessories, str):
            accessories = [item.strip() for item in accessories.replace("，", ",").split(",") if item.strip()]
        if not isinstance(accessories, list):
            accessories = []
        tags = data.get("style_tags", [])
        if isinstance(tags, str):
            tags = [item.strip() for item in tags.replace("，", ",").split(",") if item.strip()]
        if not isinstance(tags, list):
            tags = []
        tags = list(dict.fromkeys(text(tag).lower() for tag in tags if text(tag) != "unknown"))
        result = {
            "character_type": mapped("character_type", data.get("character_type")),
            "gender": mapped("gender", data.get("gender")),
            "hair": {"color": color, "style": style, "length": text(hair.get("length", data.get("hair_length")))},
            "face": {"eye_color": text(face.get("eye_color", data.get("eye_color"))), "expression": text(face.get("expression", data.get("expression"))), "shape": text(face.get("shape", data.get("face_shape")))},
            "outfit": {"category": text(outfit.get("category", data.get("outfit_category"))), "top": text(outfit.get("top")), "bottom": text(outfit.get("bottom")), "description": text(outfit.get("description", data.get("outfit_description"))), "accessories": [text(item) for item in accessories if text(item) != "unknown"]},
            "pose": mapped("pose", data.get("pose")),
            "style_tags": tags,
            "confidence": float(data.get("confidence", 0.0) or 0.0),
            "source": text(data.get("source"), "qwen2-vl"),
            "raw_analysis": data,
        }
        # Provider confidence can be supplied per field. Missing or weak
        # fields are surfaced to the UI so downstream generation can choose
        # conservative defaults instead of silently inventing details.
        field_confidence = data.get("field_confidence") if isinstance(data.get("field_confidence"), dict) else {}
        uncertain = []
        for field, value in (("character_type", result["character_type"]), ("gender", result["gender"]), ("hair", result["hair"]), ("face", result["face"]), ("outfit", result["outfit"]), ("pose", result["pose"]), ("style_tags", result["style_tags"])):
            confidence = field_confidence.get(field, result["confidence"])
            if value == "unknown" or (isinstance(value, dict) and all(item == "unknown" for item in value.values() if isinstance(item, str))) or confidence < 0.6:
                uncertain.append(field)
        result["uncertain_fields"] = list(dict.fromkeys(uncertain))
        result["confidence"] = max(0.0, min(1.0, result["confidence"]))
        return NormalizedCharacterFeatures.model_validate(result).model_dump(mode="json")

    async def _save_to_milvus(self, features: dict[str, Any], image_url: str) -> None:
        if self.milvus_client is None:
            return
        try:
            tags = features.get("style_tags") or []
            row = {"style_embedding": deterministic_embedding(json.dumps(features, ensure_ascii=False), 1024), "style_name": features.get("character_type", "unknown"), "tags": json.dumps(tags, ensure_ascii=False), "generation_params": "{}", "reference_image_url": image_url, "created_at": int(time.time())}
            await asyncio.to_thread(self.milvus_client.insert, collection_name="character_style_collection", data=[row])
        except Exception:
            logger.warning("Milvus feature insert failed image=%s", image_url, exc_info=True)


class RAGRetrievalAgent:
    collections = ("character_style_collection", "generation_params_collection", "material_reference_collection")

    def __init__(self, client: Any | None = None):
        self.client = client
        if self.client is None:
            try:
                from pymilvus import MilvusClient
                self.client = MilvusClient(uri=f"http://{settings.milvus_host}:{settings.milvus_port}")
            except Exception:
                logger.warning("Milvus client unavailable; retrieval will use defaults", exc_info=True)

    async def run(self, state: GenerationState) -> GenerationState:
        state["status"] = "retrieving"
        await _persist_status(state, "retrieving")
        features = state.get("character_features") or {}
        contexts: list[dict[str, Any]] = []
        if state.get("analysis_skipped"):
            state["retrieved_context"] = []
            state["retrieval_query"] = None
            state["retrieval_degraded"] = True
            state["generation_params"] = self._build_enhanced_params(features, [], state.get("generation_params"))
            return state
        degraded = False
        if self.client is not None:
            query_text = self._features_to_text(features)
            for collection, limit, dimension in ((self.collections[0], 5, 1024), (self.collections[1], 3, 768), (self.collections[2], 3, 512)):
                try:
                    vector, used_fallback = await self._embedding_async(query_text, dimension)
                    degraded = degraded or used_fallback
                    result = await asyncio.to_thread(self.client.search, collection_name=collection, data=[vector], limit=limit, output_fields=["*"])
                    contexts.extend(self._flatten_results(result, collection))
                except Exception:
                    degraded = True
                    logger.warning("Milvus search failed collection=%s task_id=%s", collection, state.get("task_id"), exc_info=True)
        state["retrieved_context"] = contexts
        state["retrieval_query"] = self._features_to_text(features)
        state["retrieval_degraded"] = degraded or self.client is None
        state["generation_params"] = self._build_enhanced_params(features, contexts, state.get("generation_params"))
        logger.info("RAG retrieval completed task_id=%s hits=%s", state.get("task_id"), len(contexts))
        return state

    @staticmethod
    def _features_to_text(features: dict[str, Any]) -> str:
        hair, outfit = features.get("hair", {}), features.get("outfit", {})
        return "; ".join([f"角色类型: {features.get('character_type', '')}", f"性别: {features.get('gender', '')}", f"头发: {hair.get('color', '')} {hair.get('style', '')} {hair.get('length', '')}", f"服装: {outfit.get('top', '')} {outfit.get('bottom', '')} {outfit.get('description', '')}", f"风格: {', '.join(features.get('style_tags', []))}"])

    @staticmethod
    def _embedding(text: str, dim: int) -> list[float]:
        # Compatibility helper for callers/tests. Production retrieval uses
        # _embedding_async, which can call a configured semantic model.
        return deterministic_embedding(text, dim)

    async def _embedding_async(self, text: str, dim: int) -> tuple[list[float], bool]:
        endpoint = settings.embedding_url
        if endpoint:
            try:
                headers = {"Authorization": f"Bearer {settings.embedding_api_key}"} if settings.embedding_api_key else {}
                async with httpx.AsyncClient(timeout=settings.embedding_timeout) as client:
                    response = await client.post(endpoint.rstrip("/") + "/embeddings", headers=headers, json={"model": settings.embedding_model, "input": text, "dimensions": dim})
                    response.raise_for_status()
                    payload = response.json()
                    vector = payload.get("data", [{}])[0].get("embedding") if isinstance(payload, dict) else None
                    if isinstance(vector, list) and len(vector) == dim:
                        return [float(item) for item in vector], False
                    logger.warning("Embedding provider returned dimension mismatch expected=%s", dim)
            except Exception:
                logger.warning("Embedding provider unavailable; using degraded deterministic vector", exc_info=True)
        return deterministic_embedding(text, dim), True

    @staticmethod
    def _flatten_results(results: Any, collection: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if isinstance(results, dict):
            return [{"collection": collection, **results}]
        for group in results or []:
            if isinstance(group, dict):
                rows.append({"collection": collection, **group})
                continue
            for item in (group or []):
                if isinstance(item, dict):
                    rows.append({"collection": collection, **item})
        return rows

    @staticmethod
    def _build_enhanced_params(features: dict[str, Any], contexts: list[dict[str, Any]], existing: dict[str, Any] | None) -> dict[str, Any]:
        params: dict[str, Any] = {"mesh_density": "medium", "texture_resolution": "2048", "pbr_enabled": True, "steps": 50, "guidance_scale": 7.5}
        for row in contexts:
            candidate = row.get("generation_params") or row.get("best_params")
            if isinstance(candidate, str):
                try:
                    candidate = json.loads(candidate)
                except json.JSONDecodeError:
                    candidate = None
            if isinstance(candidate, dict):
                params.update(candidate)
        if existing:
            params.update(existing)
        return params


class RetrievalRerankAgent:
    """Rank multi-collection hits and expose provenance/confidence."""

    async def run(self, state: GenerationState) -> GenerationState:
        contexts = list(state.get("retrieved_context") or [])
        ranked = sorted(contexts, key=self._rank_key, reverse=True)
        state["retrieved_context"] = ranked
        state["retrieval_sources"] = [
            {"collection": row.get("collection"), "id": row.get("id") or row.get("pk"), "score": self._score(row), "title": row.get("title") or row.get("style_name") or row.get("object_type") or row.get("material_type")}
            for row in ranked[:10]
        ]
        top_score = self._score(ranked[0]) if ranked else 0.0
        state["retrieval_confidence"] = round(max(0.0, min(1.0, top_score)), 4)
        state["generation_params"] = RAGRetrievalAgent._build_enhanced_params(state.get("character_features") or {}, ranked, state.get("generation_params"))
        logger.info("RAG rerank completed task_id=%s hits=%s confidence=%s", state.get("task_id"), len(ranked), state["retrieval_confidence"])
        return state

    @staticmethod
    def _score(row: dict[str, Any]) -> float:
        for key in ("score", "distance", "similarity"):
            try:
                value = float(row.get(key))
                # Milvus COSINE distance is normally a similarity in [0, 1].
                return max(0.0, min(1.0, value))
            except (TypeError, ValueError):
                continue
        try:
            return max(0.0, min(1.0, float(row.get("avg_quality_score", 0.0) or 0.0)))
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _rank_key(cls, row: dict[str, Any]) -> tuple[float, float]:
        try:
            success_rate = float(row.get("success_rate", 0.0) or 0.0)
        except (TypeError, ValueError):
            success_rate = 0.0
        return cls._score(row), success_rate


class ModelGenerationAgent:
    ENGINES = {"trellis2": Trellis2Service, "triposr": TripoSRService}

    async def run(self, state: GenerationState) -> GenerationState:
        state["status"] = "generating"
        await _persist_status(state, "generating")
        try:
            engine = EngineName(self._select_engine(state))
            request = build_generation_request(state, engine)
            # Keep the effective tier values in the state so persistence and
            # the task detail view describe the runner that actually ran.
            state["generation_params"] = {
                **(state.get("generation_params") or {}),
                "engine": request.engine.value,
                "generation_mode": request.mode.value,
                "texture_resolution": request.texture_resolution,
                "mesh_density": request.mesh_density,
                "pbr_enabled": request.pbr_enabled,
                "output_format": request.output_format,
            }
            service = self.ENGINES[engine.value]()
            if hasattr(service, "generate"):
                result = await service.generate(request)
            else:
                raw_result = await service.generate_async({**GenerationEngineClient._payload(request), "task_id": request.task_id})
                result = GenerationEngineClient._parse_response({"engine": engine.value, **raw_result})
            model_url = result.model_url
            if not model_url:
                raise GenerationServiceError(result.message or "generation service returned no model_url")
            state["generated_model_url"] = model_url
            state["generated_artifact_path"] = result.artifact_path
            state["generated_textures"] = result.texture_urls
            state["generation_metadata"] = {"engine": result.engine.value, "mode": request.mode.value, **result.metadata}
            # Persist the concrete provider alongside the requested tier so
            # the task UI can explain whether this run used local ComfyUI,
            # TripoSR, a command runner, or a remote demo.
            if result.metadata.get("provider"):
                state["generation_params"]["provider"] = result.metadata["provider"]
            if result.metadata.get("provider_model"):
                state["generation_params"]["provider_model"] = result.metadata["provider_model"]
            if result.metadata.get("sampling_seed") is not None:
                state["generation_params"]["seed"] = result.metadata["sampling_seed"]
            state["generation_mode"] = request.mode.value
            state["generation_job_id"] = result.job_id
            state["error_message"] = None
        except Exception as exc:
            state["generated_model_url"] = None
            state["error_message"] = f"Model generation failed: {exc}"
            state["status"] = "failed"
            await _persist_status(state, "failed")
            logger.exception("Model generation failed task_id=%s", state.get("task_id"))
        return state

    @staticmethod
    def _select_engine(state: GenerationState):
        return select_engine(state).value


class QualityCheckAgent:
    async def run(self, state: GenerationState) -> GenerationState:
        if not state.get("quality_checks"):
            state = await DeterministicQualityCheckAgent().run(state)
        # The graph has a dedicated quality_retrieve node.  Only invoke the
        # compatibility fallback when that node was not run at all; an empty
        # list is a valid degraded/no-hit result and must not trigger a second
        # vector search.
        if "quality_repair_suggestions" not in state and any(not ok for ok in (state.get("quality_checks") or {}).values()):
            state = await QualityRepairRAGAgent().run(state)
        state["status"] = "evaluating"
        await _persist_status(state, "evaluating")
        metadata = state.get("generation_metadata") or {}
        try:
            face_count = int(metadata.get("face_count", 1000) or 0)
        except (TypeError, ValueError):
            face_count = 0
        mode = DeterministicQualityCheckAgent._resolve_mode(state, metadata)
        checks = state.get("quality_checks") or {}
        score = round(sum(checks.values()) / len(checks), 4)
        state["quality_score"] = score
        failed_checks = [name for name, passed in checks.items() if not passed]
        warnings = [f"{name} check failed" for name in failed_checks]
        state["generation_metadata"] = {
            **metadata,
            "quality_mode": mode.value,
            "quality_checks": checks,
            "quality_warnings": warnings,
            "quality_repair_suggestions": state.get("quality_repair_suggestions") or [],
            "quality_repair_sources": state.get("quality_repair_sources") or [],
            "quality_repair_degraded": bool(state.get("quality_repair_degraded", False)),
        }
        retries = int(state.get("retry_count", 0))
        # Single-image reconstruction often produces an open surface. Both
        # local TripoSR tiers surface topology warnings without blocking
        # delivery; the remote TRELLIS.2 tier remains strict for final output.
        required_checks = ("face_count_ok", "no_degenerate", "texture_resolution_ok")
        if mode == GenerationMode.HIGH_QUALITY and (state.get("generation_metadata") or {}).get("provider") != "local_comfyui":
            required_checks += ("watertight", "manifold")
        if all(checks[name] for name in required_checks):
            state["evaluation_result"] = "pass"
        elif retries < 3:
            state["evaluation_result"] = "retry"
            state["retry_count"] = retries + 1
            state["generation_params"] = DeterministicQualityCheckAgent._adjust_params(state.get("generation_params") or {}, checks)
        else:
            state["evaluation_result"] = "fail"
            state["status"] = "failed"
            state["error_message"] = f"Quality check failed: {checks}"
            await _persist_status(state, "failed")
        logger.info("Quality check task_id=%s score=%s result=%s", state.get("task_id"), score, state["evaluation_result"])
        return state


class DeterministicQualityCheckAgent:
    """Run objective mesh/texture checks without an LLM or vector search."""

    async def run(self, state: GenerationState) -> GenerationState:
        state["status"] = "evaluating"
        await _persist_status(state, "evaluating")
        metadata = state.get("generation_metadata") or {}
        inspected = await DeterministicQualityCheckAgent._inspect_local_mesh(
            state.get("generated_artifact_path") or state.get("generated_model_url")
        )
        if inspected:
            metadata = {**metadata, **inspected}
            state["generation_metadata"] = metadata
        try:
            face_count = int(metadata.get("face_count", 1000) or 0)
        except (TypeError, ValueError):
            face_count = 0
        checks = {
            "watertight": bool(metadata.get("watertight", False)),
            "manifold": bool(metadata.get("manifold", False)),
            "face_count_ok": 100 < face_count < (750000 if metadata.get("provider") == "local_comfyui" else 500000),
            "no_degenerate": metadata.get("degenerate_faces", 0) == 0,
            "texture_resolution_ok": DeterministicQualityCheckAgent._texture_ok(
                metadata.get("texture_resolution", (state.get("generation_params") or {}).get("texture_resolution", "2048"))
            ),
        }
        state["quality_checks"] = checks
        state["quality_score"] = round(sum(checks.values()) / len(checks), 4)
        state["generation_metadata"] = {
            **metadata,
            "quality_checks": checks,
            "quality_warnings": [f"{name} check failed" for name, passed in checks.items() if not passed],
        }
        return state

    @staticmethod
    def _resolve_mode(state: GenerationState, metadata: dict[str, Any]) -> GenerationMode:
        params = state.get("generation_params") or {}
        raw_mode = state.get("generation_mode") or params.get("mode") or params.get("generation_mode") or metadata.get("mode")
        if raw_mode:
            normalized = str(raw_mode).lower().replace("-", "_")
            if normalized == GenerationMode.FAST.value:
                return GenerationMode.FAST
            if normalized in {"preview", "quick", GenerationMode.QUICK_PREVIEW.value}:
                return GenerationMode.QUICK_PREVIEW
            if normalized in {GenerationMode.BALANCED.value, "standard"}:
                return GenerationMode.BALANCED
            if normalized in {"quality", "high", GenerationMode.HIGH_QUALITY.value}:
                return GenerationMode.HIGH_QUALITY
        engine = params.get("engine") or metadata.get("engine")
        if engine and str(engine).lower().replace("-", "") == EngineName.TRIPOSR.value:
            return GenerationMode.QUICK_PREVIEW
        return GenerationMode.HIGH_QUALITY

    @staticmethod
    async def _inspect_local_mesh(model_url: str | None) -> dict[str, Any]:
        if not model_url or model_url.startswith(("http://", "https://", "s3://", "upload://")) or not Path(model_url).exists():
            return {}
        try:
            import trimesh
            mesh = await asyncio.to_thread(trimesh.load, model_url, force="mesh")
            faces = mesh.faces
            degenerate = ((faces[:, 0] == faces[:, 1]) | (faces[:, 1] == faces[:, 2]) | (faces[:, 0] == faces[:, 2])).sum()
            return {"watertight": bool(mesh.is_watertight), "manifold": bool(mesh.is_watertight and mesh.is_winding_consistent),
                    "vertex_count": int(len(mesh.vertices)), "face_count": int(len(faces)), "degenerate_faces": int(degenerate),
                    "file_size_mb": Path(model_url).stat().st_size / (1024 * 1024),
                    "bounding_box": {"min": mesh.bounds[0].tolist(), "max": mesh.bounds[1].tolist()}}
        except Exception:
            logger.warning("Local mesh inspection failed path=%s", model_url, exc_info=True)
            return {}

    @staticmethod
    def _texture_ok(value: Any) -> bool:
        try:
            return int(str(value).replace("K", "")) >= 512
        except (TypeError, ValueError):
            return True

    @staticmethod
    def _adjust_params(params: dict[str, Any], checks: dict[str, bool]) -> dict[str, Any]:
        updated = dict(params)
        if not checks.get("face_count_ok", True): updated["mesh_density"] = "high"
        if not checks.get("texture_resolution_ok", True): updated["texture_resolution"] = "2048"
        updated["quality_retry"] = True
        return updated


class QualityRepairRAGAgent:
    """Retrieve repair examples only after deterministic checks identify failures."""

    def __init__(self, client: Any | None = None):
        self.client = client
        if self.client is None:
            try:
                from pymilvus import MilvusClient
                self.client = MilvusClient(uri=f"http://{settings.milvus_host}:{settings.milvus_port}")
            except Exception:
                logger.warning("Milvus client unavailable; quality repair RAG degraded", exc_info=True)

    async def run(self, state: GenerationState) -> GenerationState:
        checks = state.get("quality_checks") or {}
        failed = [name for name, passed in checks.items() if not passed]
        state["quality_repair_suggestions"] = []
        state["quality_repair_sources"] = []
        state["quality_repair_degraded"] = False
        if not failed or self.client is None:
            state["quality_repair_degraded"] = bool(failed)
            return state
        query = f"task_type={state.get('task_type', '')}; failed_checks={', '.join(failed)}"
        try:
            vector, degraded = await RAGRetrievalAgent(client=self.client)._embedding_async(query, 768)
            rows = await asyncio.to_thread(
                self.client.search,
                collection_name="generation_params_collection",
                data=[vector],
                limit=5,
                output_fields=["*"],
            )
            contexts = RAGRetrievalAgent._flatten_results(rows, "generation_params_collection")
            state["quality_repair_degraded"] = degraded
            for row in contexts:
                suggestion = row.get("quality_repair") or row.get("repair_params") or row.get("best_params") or row.get("generation_params")
                if isinstance(suggestion, str):
                    try:
                        suggestion = json.loads(suggestion)
                    except json.JSONDecodeError:
                        suggestion = {"note": suggestion}
                if isinstance(suggestion, dict):
                    state["quality_repair_suggestions"].append({"failed_checks": failed, "suggestion": suggestion})
                state["quality_repair_sources"].append({
                    "collection": row.get("collection"),
                    "id": row.get("id") or row.get("pk"),
                    "score": RAGRetrievalAgent._score(row),
                    "title": row.get("title") or row.get("style_name") or "质量修复案例",
                })
        except Exception:
            state["quality_repair_degraded"] = True
            logger.warning("Quality repair RAG failed task_id=%s", state.get("task_id"), exc_info=True)
        return state

class PostProcessAgent:
    async def run(self, state: GenerationState) -> GenerationState:
        state["status"] = "postprocessing"
        await _persist_status(state, "postprocessing")
        state["status"] = "completed"
        state["error_message"] = None
        logger.info("Postprocessing completed task_id=%s", state.get("task_id"))
        return state


class MasterAgent:
    def __init__(self) -> None:
        graph = StateGraph(GenerationState)
        retrieval_agent = RAGRetrievalAgent()
        graph.add_node("init", self._init_task)
        graph.add_node("analyze", CharacterAnalysisAgent(retrieval_agent.client).run)
        graph.add_node("normalize", CharacterNormalizationAgent(retrieval_agent.client).run)
        graph.add_node("retrieve", retrieval_agent.run)
        graph.add_node("rerank", RetrievalRerankAgent().run)
        graph.add_node("generate", ModelGenerationAgent().run)
        graph.add_node("inspect_quality", DeterministicQualityCheckAgent().run)
        graph.add_node("quality_retrieve", QualityRepairRAGAgent(retrieval_agent.client).run)
        graph.add_node("evaluate", QualityCheckAgent().run)
        graph.add_node("postprocess", PostProcessAgent().run)
        graph.set_entry_point("init")
        graph.add_edge("init", "analyze")
        graph.add_conditional_edges("analyze", lambda s: "normalize" if s.get("status") != "failed" else "fail", {"normalize": "normalize", "fail": END})
        graph.add_conditional_edges("normalize", lambda s: "retrieve" if s.get("status") != "failed" else "fail", {"retrieve": "retrieve", "fail": END})
        graph.add_edge("retrieve", "rerank")
        graph.add_edge("rerank", "generate")
        graph.add_conditional_edges("generate", lambda s: "inspect_quality" if s.get("generated_model_url") else "fail", {"inspect_quality": "inspect_quality", "fail": END})
        graph.add_edge("inspect_quality", "quality_retrieve")
        graph.add_edge("quality_retrieve", "evaluate")
        graph.add_conditional_edges("evaluate", self._route_after_evaluate, {"pass": "postprocess", "retry": "generate", "fail": END})
        graph.add_edge("postprocess", END)
        self.workflow = graph.compile()

    @staticmethod
    async def _init_task(state: GenerationState) -> GenerationState:
        state.setdefault("status", "pending")
        state.setdefault("retry_count", 0)
        state.setdefault("generation_params", {})
        return state

    @staticmethod
    def _route_after_evaluate(state: GenerationState) -> str:
        if state.get("evaluation_result") == "pass": return "pass"
        if state.get("evaluation_result") == "retry" and int(state.get("retry_count", 0)) <= 3: return "retry"
        return "fail"


master_agent = MasterAgent()
workflow = master_agent.workflow


def build_workflow():
    return MasterAgent().workflow
