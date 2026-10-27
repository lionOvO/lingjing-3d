"""Authenticated asset organization and reusable generation presets."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db_session
from .models import GenerationPreset, GenerationTask, GenerationTaskStatus, ModelMetadata, Project, StudioAsset, StudioAssetTrash, User
from .security import get_current_user
from .storage import StorageError, storage

router = APIRouter(prefix="/api/v1/studio", tags=["studio"])


class AssetLabel(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("名称不能为空")
        return value.strip()

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, values):
        if any(not value.strip() or len(value.strip()) > 24 for value in values):
            raise ValueError("标签需为 1–24 个字符")
        return list(dict.fromkeys(value.strip() for value in values))


class PresetParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generation_mode: Literal["high_quality"] = "high_quality"
    texture_resolution: Literal["1024", "2048"] = "1024"
    mesh_density: Literal["low", "medium", "high"] = "medium"
    pbr_enabled: Literal[True] = True
    seed: int | None = Field(default=None, ge=0, le=2147483647)


class PresetInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    project_type: Literal["anime_character", "object_model"] = "anime_character"
    parameters: PresetParameters = Field(default_factory=PresetParameters)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("名称不能为空")
        return value.strip()


async def owned_task(task_id: int, user: User, db: AsyncSession):
    row = (await db.execute(select(GenerationTask, Project).join(Project).where(GenerationTask.id == task_id, Project.user_id == user.id))).first()
    if not row or row[0].status != GenerationTaskStatus.COMPLETED or not row[0].output_model_url:
        raise HTTPException(404, "模型资产不存在")
    return row


@router.get("/assets")
async def assets(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session), offset: int = Query(0, ge=0), limit: int = Query(60, ge=1, le=100), deleted: bool = False):
    rows = (await db.execute(select(GenerationTask, Project, StudioAsset, ModelMetadata).join(Project).outerjoin(StudioAsset, StudioAsset.task_id == GenerationTask.id).outerjoin(ModelMetadata, ModelMetadata.task_id == GenerationTask.id).outerjoin(StudioAssetTrash, StudioAssetTrash.task_id == GenerationTask.id).where(Project.user_id == user.id, GenerationTask.status == GenerationTaskStatus.COMPLETED, GenerationTask.output_model_url.is_not(None), StudioAssetTrash.task_id.is_not(None) if deleted else StudioAssetTrash.task_id.is_(None)).order_by(GenerationTask.id.desc()).offset(offset).limit(limit))).all()
    return [{"id": task.id, "project_id": project.id, "project_name": project.name, "name": label.name if label else f"{project.name} · #{task.id}", "tags": label.tags if label else [], "project_type": task.task_type.value, "format": task.output_format.value, "created_at": task.created_at, "quality_score": task.quality_score, "parameters": {key: value for key, value in (task.generation_params or {}).items() if not key.startswith("_")}, "preview_available": bool((task.generation_params or {}).get("_artifact_object_name")), "metadata": {"vertex_count": meta.vertex_count, "face_count": meta.face_count, "file_size_mb": meta.file_size_mb, "texture_resolution": meta.texture_resolution, "has_pbr": meta.has_pbr} if meta else {}} for task, project, label, meta in rows]


@router.put("/assets/{task_id}")
async def label_asset(task_id: int, payload: AssetLabel, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    await owned_task(task_id, user, db)
    label = await db.get(StudioAsset, task_id)
    if label is None:
        label = StudioAsset(task_id=task_id, **payload.model_dump())
        db.add(label)
    else:
        label.name, label.tags = payload.name, payload.tags
    await db.commit()
    return {"id": task_id, **payload.model_dump()}


@router.delete("/assets/{task_id}")
async def trash_asset(task_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    await owned_task(task_id, user, db)
    if await db.get(StudioAssetTrash, task_id) is None:
        db.add(StudioAssetTrash(task_id=task_id))
        await db.commit()
    return {"id": task_id, "deleted": True}


@router.post("/assets/{task_id}/restore")
async def restore_asset(task_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    await owned_task(task_id, user, db)
    entry = await db.get(StudioAssetTrash, task_id)
    if entry is not None:
        await db.delete(entry)
        await db.commit()
    return {"id": task_id, "deleted": False}


@router.get("/assets/{task_id}/file")
async def asset_file(task_id: int, download: bool = False, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    task, _ = await owned_task(task_id, user, db)
    object_name = (task.generation_params or {}).get("_artifact_object_name")
    if not object_name:
        # Do not materialize legacy mock records or generate substitute geometry.
        raise HTTPException(404, "此历史记录未保存可读取的模型文件")
    try:
        data, content_type = await storage.get_object(str(object_name))
    except StorageError as exc:
        raise HTTPException(404, "模型文件暂时不可用") from exc
    headers = {"Cache-Control": "private, no-store"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="lingjing-model-{task.id}.{task.output_format.value}"'
    return Response(content=data, media_type=content_type, headers=headers)


def preset_record(preset):
    return {"id": preset.id, "name": preset.name, "project_type": preset.project_type, "parameters": preset.parameters, "created_at": preset.created_at}


@router.get("/presets")
async def presets(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    rows = await db.scalars(select(GenerationPreset).where(GenerationPreset.user_id == user.id, GenerationPreset.archived.is_(False)).order_by(GenerationPreset.id.desc()))
    return [preset_record(row) for row in rows]


@router.post("/presets", status_code=201)
async def create_preset(payload: PresetInput, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    preset = GenerationPreset(user_id=user.id, name=payload.name, project_type=payload.project_type, parameters=payload.parameters.model_dump(), archived=False)
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return preset_record(preset)


@router.put("/presets/{preset_id}")
async def update_preset(preset_id: int, payload: PresetInput, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    preset = await db.get(GenerationPreset, preset_id)
    if not preset or preset.user_id != user.id or preset.archived:
        raise HTTPException(404, "预设不存在")
    preset.name, preset.project_type, preset.parameters = payload.name, payload.project_type, payload.parameters.model_dump()
    await db.commit()
    return preset_record(preset)


@router.delete("/presets/{preset_id}")
async def archive_preset(preset_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    preset = await db.get(GenerationPreset, preset_id)
    if not preset or preset.user_id != user.id:
        raise HTTPException(404, "预设不存在")
    preset.archived = True
    await db.commit()
    return {"archived": True}
