"""Celery entry points for running the async agent workflow."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from celery import Celery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from .agents import workflow
from .config import settings
from .models import CharacterFeature, GenerationTask, GenerationTaskStatus, ModelMetadata, Project, ProjectStatus
from .storage import StorageError, storage

logger = logging.getLogger("digital_human.worker")

celery_app = Celery("digital-human", broker=settings.celery_broker_url, backend=settings.celery_result_backend)
celery_app.conf.update(
    task_track_started=True,
    # The 3D workflow can run for many minutes. Acknowledge only after it
    # finishes so a worker/container restart puts an in-flight task back on
    # the Redis queue instead of leaving its database status at "analyzing".
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    task_default_queue="generation",
    task_routes={"generate_3d": {"queue": "generation"}},
    result_expires=86400,
)


def _worker_engine_options() -> dict:
    """Avoid retaining aiomysql connections across Celery's event loops."""
    return {
        "pool_pre_ping": False,
        "pool_recycle": 1800,
        "echo": settings.sql_echo,
        "poolclass": NullPool,
    }


@asynccontextmanager
async def worker_db_session():
    """Provide a database session bound only to the current Celery task loop."""
    engine = create_async_engine(settings.database_url, **_worker_engine_options())
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            yield session
    finally:
        await engine.dispose()


async def run_generation_task(task_id: str, image_url: str | None = None) -> dict:
    async with worker_db_session() as db:
        task = await db.get(GenerationTask, int(task_id))
        if task is None:
            raise ValueError(f"Generation task {task_id} not found")
        project = await db.get(Project, task.project_id)
        source_url = image_url or (project.source_image_url if project else None)
        async def persist_status(status: str) -> None:
            """Commit stage changes before a long-running node starts."""
            task.status = GenerationTaskStatus(status)
            task.error_message = None
            await db.commit()
            logger.info("Generation task stage task_id=%s status=%s", task.id, status)

        state = {"task_id": str(task.id), "project_id": task.project_id, "task_type": task.task_type.value, "source_image_url": source_url or "", "output_format": task.output_format.value, "generation_params": task.generation_params or {}, "retry_count": task.retry_count, "status_callback": persist_status}
        try:
            task.status = GenerationTaskStatus.ANALYZING
            await db.commit()
            result: dict = state
            # LangGraph emits a complete state after each node. Persist the
            # stage immediately so the API websocket can report actual work,
            # rather than a fabricated client-side progress bar.
            async for update in workflow.astream(state, stream_mode="values"):
                result = dict(update)
                status_value = result.get("status")
                if status_value in {item.value for item in GenerationTaskStatus}:
                    candidate = GenerationTaskStatus(status_value)
                    # The graph emits its initial `pending` snapshot after
                    # the API has already marked the task as analyzing. Do
                    # not let an older snapshot move a task backwards.
                    if not (task.status != GenerationTaskStatus.PENDING and candidate == GenerationTaskStatus.PENDING):
                        task.status = candidate
                        task.error_message = result.get("error_message")
                        if "character_features" in result:
                            task.analysis_result = result.get("character_features")
                        # Quality inspection and repair run after generation;
                        # persist their diagnostics as soon as each node emits
                        # state so the desktop task page can explain failures
                        # while a retry is still being prepared.
                        if any(key in result for key in ("quality_checks", "quality_repair_suggestions", "quality_repair_sources", "quality_repair_degraded")):
                            current_retrieval = dict(task.retrieved_params or {})
                            for key in ("quality_checks", "quality_repair_suggestions", "quality_repair_sources", "quality_repair_degraded"):
                                if key in result:
                                    current_retrieval[key] = result.get(key)
                            task.retrieved_params = current_retrieval
                        if any(key in result for key in ("retrieved_context", "retrieval_sources", "retrieval_confidence", "retrieval_query", "retrieval_degraded")):
                            current_retrieval = dict(task.retrieved_params or {})
                            current_retrieval.update({
                                "context": result.get("retrieved_context") or current_retrieval.get("context", []),
                                "sources": result.get("retrieval_sources") or current_retrieval.get("sources", []),
                                "confidence": result.get("retrieval_confidence"),
                                "degraded": bool(result.get("retrieval_degraded", False)),
                                "query": result.get("retrieval_query"),
                            })
                            task.retrieved_params = current_retrieval
                        await db.commit()
            # A real engine writes its artifact to the shared GPU volume. Move
            # that file into private MinIO before exposing it to the API.
            artifact_path = result.get("generated_artifact_path")
            if result.get("status") == "completed" and artifact_path:
                artifact = await _read_engine_artifact(str(artifact_path))
                object_name = await storage.upload_generated_model(task.id, artifact, task.output_format.value)
                params = dict(result.get("generation_params") or {})
                params["_artifact_object_name"] = object_name
                result["generation_params"] = params
                result["generated_model_url"] = f"/api/v1/models/{task.id}/content"
                result["generated_artifact_path"] = None
                try:
                    Path(artifact_path).unlink(missing_ok=True)
                except OSError:
                    logger.warning("Unable to remove temporary engine artifact path=%s", artifact_path, exc_info=True)
            task.status = _task_status(result.get("status", "failed"))
            task.analysis_result = result.get("character_features")
            task.retrieved_params = {
                "context": result.get("retrieved_context") or [],
                "sources": result.get("retrieval_sources") or [],
                "confidence": result.get("retrieval_confidence"),
                "degraded": bool(result.get("retrieval_degraded", False)),
                "query": result.get("retrieval_query"),
                "quality_checks": result.get("quality_checks") or {},
                "quality_repair_suggestions": result.get("quality_repair_suggestions") or [],
                "quality_repair_sources": result.get("quality_repair_sources") or [],
                "quality_repair_degraded": bool(result.get("quality_repair_degraded", False)),
            }
            task.generation_params = result.get("generation_params")
            task.quality_score = result.get("quality_score")
            task.output_model_url = result.get("generated_model_url")
            task.texture_urls = result.get("generated_textures")
            task.error_message = result.get("error_message")
            task.retry_count = int(result.get("retry_count", task.retry_count))
            features = result.get("character_features") or {}
            if features and task.task_type.value == "anime_character":
                feature = await db.scalar(select(CharacterFeature).where(CharacterFeature.task_id == task.id))
                if feature is None:
                    feature = CharacterFeature(task_id=task.id)
                    db.add(feature)
                hair, face, outfit = features.get("hair") or {}, features.get("face") or {}, features.get("outfit") or {}
                feature.character_type = features.get("character_type")
                feature.gender = features.get("gender")
                feature.hair_color = hair.get("color")
                feature.hair_style = hair.get("style")
                feature.eye_color = face.get("eye_color")
                feature.outfit_description = outfit.get("description") or outfit.get("top")
                feature.pose = features.get("pose")
                feature.style_tags = features.get("style_tags")
            metadata = result.get("generation_metadata") or {}
            if metadata or result.get("quality_score") is not None:
                model_metadata = await db.scalar(select(ModelMetadata).where(ModelMetadata.task_id == task.id))
                if model_metadata is None:
                    model_metadata = ModelMetadata(task_id=task.id)
                    db.add(model_metadata)
                model_metadata.vertex_count = metadata.get("vertex_count")
                model_metadata.face_count = metadata.get("face_count")
                model_metadata.texture_resolution = metadata.get("texture_resolution")
                model_metadata.has_pbr = bool(metadata.get("has_pbr", (task.generation_params or {}).get("pbr_enabled", False)))
                model_metadata.file_size_mb = metadata.get("file_size_mb")
                model_metadata.bounding_box = metadata.get("bounding_box")
            if task.status == GenerationTaskStatus.COMPLETED:
                task.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                if project:
                    project.status = ProjectStatus.COMPLETED
            elif task.status == GenerationTaskStatus.FAILED and project:
                project.status = ProjectStatus.FAILED
            await db.commit()
            # The callback is worker-local and must not enter Celery's JSON
            # result backend.
            result.pop("status_callback", None)
            return dict(result)
        except Exception as exc:
            await db.rollback()
            task = await db.get(GenerationTask, int(task_id))
            if task:
                task.status = GenerationTaskStatus.FAILED
                task.error_message = str(exc)
                if project:
                    project.status = ProjectStatus.FAILED
                await db.commit()
            logger.exception("Generation task failed task_id=%s", task_id)
            raise


def _task_status(status: str) -> GenerationTaskStatus:
    try:
        return GenerationTaskStatus(status)
    except ValueError:
        return GenerationTaskStatus.FAILED


def _fallback_model(output_format: str) -> bytes:
    """Build a small valid mesh artifact for adapter-only deployments."""
    import trimesh

    mesh = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
    mesh.visual.vertex_colors = [232, 169, 197, 255]
    if output_format == "fbx":
        # trimesh has no FBX exporter. This minimal ASCII FBX triangle is a
        # valid, portable fallback for adapter-only deployments.
        return b'; FBX 7.4.0 project file\nFBXHeaderExtension:  {\n FBXHeaderVersion: 1003\n FBXVersion: 7400\n}\nObjects:  {\n Geometry: 1, "Geometry::MoonlitFallback", "Mesh" {\n  Vertices: *9 { a:0,0,0,1,0,0,0,1,0 }\n  PolygonVertexIndex: *3 { a:0,1,-3 }\n }\n}\nConnections:  {\n}\n'
    file_type = "glb" if output_format == "glb" else output_format
    exported = mesh.export(file_type=file_type)
    return exported.encode("utf-8") if isinstance(exported, str) else bytes(exported)


async def _read_engine_artifact(path: str) -> bytes:
    """Read only files produced inside the configured shared artifact volume."""
    root = Path(settings.trellis_artifact_dir).resolve()
    candidate = Path(path).resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError("engine artifact path is outside the shared artifact directory")
    if candidate.suffix.lower().lstrip(".") not in {"glb", "obj", "fbx", "stl"}:
        raise ValueError("real generation produced an unsupported model format")
    if not candidate.is_file():
        raise FileNotFoundError(f"engine artifact not found: {candidate}")
    data = await asyncio.to_thread(candidate.read_bytes)
    if not data:
        raise ValueError("engine artifact is empty")
    if candidate.suffix.lower() == ".glb" and data[:4] != b"glTF":
        raise ValueError("engine artifact is not a valid GLB file")
    return data


@celery_app.task(name="generate_3d", bind=True, autoretry_for=(), max_retries=0)
def generate_3d(self, task_id: str, image_url: str | None = None):
    """Synchronous Celery wrapper around the async SQLAlchemy workflow."""
    return asyncio.run(run_generation_task(task_id, image_url))
