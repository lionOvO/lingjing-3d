"""Authenticated image preparation and non-destructive model repair."""
import asyncio
import base64
import io

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from typing import Literal
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import get_db_session
from .models import GenerationTask, Project, ModelInspection, ModelRevision
from .security import get_current_user
from .storage import storage, StorageError
from .studio import owned_task
from .mesh_tools import inspect_glb, repair_glb
from .reference_tools import analyze_reference
from .deepseek_vision import inspect_preparation

router = APIRouter(prefix="/api/v1/studio", tags=["creation tools"])
mesh_slots = asyncio.Semaphore(1)


class ImportImage(BaseModel):
    url: HttpUrl


class ForegroundCrop(BaseModel):
    model_config = ConfigDict(extra='forbid')
    x: float = Field(ge=0, lt=100)
    y: float = Field(ge=0, lt=100)
    width: float = Field(gt=0, le=100)
    height: float = Field(gt=0, le=100)

    @model_validator(mode='after')
    def within_image(self):
        if self.x + self.width > 100.001 or self.y + self.height > 100.001:
            raise ValueError('框选范围超出图片')
        return self


@router.post("/images/import-url")
async def import_image(payload: ImportImage, user=Depends(get_current_user)):
    """Use the existing URL uploader, returning pixels without queueing a task."""
    stored = None
    try:
        stored = await storage.upload_url(str(payload.url))
        data, content_type = await storage.get_object(stored.object_name)
        return Response(data, media_type=content_type, headers={"Cache-Control":"private, no-store"})
    except StorageError:
        raise HTTPException(422, "图片链接无法读取，请下载后本地上传") from None
    finally:
        if stored is not None:
            await storage.delete(stored.object_name)


@router.get("/tasks/{task_id}/input")
async def task_input(task_id: int, original: bool = False, user=Depends(get_current_user), db: AsyncSession=Depends(get_db_session)):
    row = (await db.execute(select(GenerationTask,Project).join(Project,GenerationTask.project_id==Project.id).where(GenerationTask.id==task_id,Project.user_id==user.id))).first()
    if not row:
        raise HTTPException(404,"任务不存在")
    task,project=row
    params=task.generation_params or {}
    name=params.get("_original_source_object_name" if original else "_source_object_name")
    kind="snapshot"
    if not name and not original:
        name=storage.object_name_from_url(project.source_image_url)
        kind="project_current"
    if not name:
        raise HTTPException(404,"此历史任务未保存该输入图片")
    try:
        data,content_type=await storage.get_object(name)
    except StorageError:
        raise HTTPException(404,"输入图片暂时不可用") from None
    return Response(data,media_type=content_type,headers={"Cache-Control":"private, no-store","X-Input-Kind":kind})


async def source(task_id, user, db):
    task, project = await owned_task(task_id, user, db)
    if task.output_format.value != "glb":
        raise HTTPException(422, "检查与修复目前支持 GLB，请使用原格式下载其他模型")
    name = (task.generation_params or {}).get("_artifact_object_name")
    if not name:
        raise HTTPException(404, "历史记录没有保存原始模型文件")
    try:
        data, _ = await storage.get_object(name)
    except StorageError:
        raise HTTPException(404, "模型原文件暂时不可用") from None
    return task, project, data


def revision_record(row):
    return {"id": row.id, "task_id": row.task_id, "name": row.name, "report": row.report, "options": row.options, "created_at": row.created_at}


@router.get("/assets/{task_id}/inspection")
async def saved_inspection(task_id: int, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    await owned_task(task_id, user, db)
    inspection = await db.get(ModelInspection, task_id)
    rows = await db.scalars(select(ModelRevision).where(ModelRevision.task_id == task_id).order_by(ModelRevision.id.desc()))
    return {"report": inspection.report if inspection else None, "review": inspection.review if inspection else {}, "revisions": [revision_record(row) for row in rows]}


@router.post("/assets/{task_id}/inspect")
async def inspect(task_id: int, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    async with mesh_slots:
        _, _, data = await source(task_id, user, db)
        try:
            report = await asyncio.to_thread(inspect_glb, data)
        except (ValueError, KeyError, IndexError, TypeError):
            raise HTTPException(422, "无法检查此 GLB：请确认模型有效、已内嵌贴图且不超过 80MB / 200 万面") from None
        row = await db.get(ModelInspection, task_id)
        if row is None:
            row = ModelInspection(task_id=task_id, report=report, review={})
            db.add(row)
        else:
            row.report = report
        await db.commit()
        return report


class RepairInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    clean_faces: bool = True
    fix_winding: bool = True
    fill_holes: bool = False


@router.post("/assets/{task_id}/repair", status_code=201)
async def repair(task_id: int, payload: RepairInput, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    if not payload.name.strip() or not (payload.clean_faces or payload.fix_winding or payload.fill_holes):
        raise HTTPException(422, "请输入版本名称并至少选择一项修复操作")
    async with mesh_slots:
        _, _, data = await source(task_id, user, db)
        options = payload.model_dump(exclude={"name"})
        try:
            result, report = await asyncio.to_thread(repair_glb, data, options)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else "此模型无法安全修复，请下载后在建模软件中处理") from None
        try:
            name = await storage.upload_generated_model(task_id, result, "glb")
        except StorageError:
            raise HTTPException(503, "修复结果暂时无法保存，请稍后重试") from None
        row = ModelRevision(task_id=task_id, name=payload.name.strip(), object_name=name, report=report, options=options)
        db.add(row)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            await storage.delete(name)
            raise
        await db.refresh(row)
        return revision_record(row)


@router.get("/assets/{task_id}/revisions/{revision_id}/file")
async def revision_file(task_id: int, revision_id: int, download: bool = False, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    await owned_task(task_id, user, db)
    row = await db.get(ModelRevision, revision_id)
    if not row or row.task_id != task_id:
        raise HTTPException(404, "修复版本不存在")
    try:
        data, _ = await storage.get_object(row.object_name)
    except StorageError:
        raise HTTPException(404, "修复文件暂时不可用") from None
    return Response(data, media_type="model/gltf-binary", headers={"Cache-Control": "private, no-store", **({"Content-Disposition": f'attachment; filename="lingjing-{task_id}-repair-{row.id}.glb"'} if download else {})})


class VisualReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    face: bool = False
    back: bool = False
    texture: bool = False
    silhouette: bool = False
    note: str = Field(default="", max_length=1000)


@router.put("/assets/{task_id}/review")
async def review(task_id: int, data: VisualReview, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    await owned_task(task_id, user, db)
    row = await db.get(ModelInspection, task_id)
    if not row:
        raise HTTPException(409, "请先运行结构检查，再保存原模型的外观复核")
    row.review = data.model_dump()
    await db.commit()
    return row.review


@router.get("/assets/{task_id}/reference")
async def reference(task_id: int, allow_current_project: bool = False, user=Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    task, project = await owned_task(task_id, user, db)
    # Historical tasks did not freeze their input. Never label a newer project image as the original.
    name = (task.generation_params or {}).get("_source_object_name")
    kind = "snapshot"
    if not name and allow_current_project:
        name = storage.object_name_from_url(project.source_image_url)
        kind = "current_project"
    if not name:
        raise HTTPException(404, "此历史任务未保存独立参考图快照")
    try:
        data, content_type = await storage.get_object(name)
    except StorageError:
        raise HTTPException(404, "参考图暂时不可用") from None
    return Response(data, media_type=content_type, headers={"Cache-Control": "private, no-store", "X-Reference-Kind": kind})


@router.post("/images/analyze-reference")
async def reference_analysis(image: UploadFile = File(...), user=Depends(get_current_user)):
    data=await image.read(20*1024*1024+1)
    if not data or len(data)>20*1024*1024:
        raise HTTPException(422,'请选择 20MB 以内的图片')
    try:
        return await asyncio.to_thread(analyze_reference,data)
    except ValueError as error:
        raise HTTPException(422,str(error)) from None


@router.get("/images/vision-status")
async def vision_status(user=Depends(get_current_user)):
    return {"configured": bool(settings.deepseek_api_key.get_secret_value().strip()), "model": settings.deepseek_model}


@router.post("/images/vision-preparation")
async def vision_preparation(image: UploadFile = File(...), candidate: UploadFile | None = File(None), user=Depends(get_current_user)):
    original = await image.read(20*1024*1024+1)
    prepared = await candidate.read(20*1024*1024+1) if candidate else None
    return await inspect_preparation(original, prepared)


@router.post("/images/remove-background")
async def remove_background(image: UploadFile = File(...), user=Depends(get_current_user), model: Literal['isnet-anime','u2net'] = Form('isnet-anime'), crop: str | None = Form(None)):
    data = await image.read(20*1024*1024 + 1)
    if not data or len(data) > 20*1024*1024:
        raise HTTPException(422, "请选择 20MB 以内的图片")
    normalized = None
    box = None
    try:
        with Image.open(io.BytesIO(data)) as candidate:
            if candidate.width*candidate.height > 20_000_000 or candidate.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError()
            candidate.verify()
        if isinstance(crop, str):
            bounds = ForegroundCrop.model_validate_json(crop)
            with Image.open(io.BytesIO(data)) as candidate:
                normalized = ImageOps.exif_transpose(candidate).convert('RGBA')
            w, h = normalized.size
            left, top = int(w*bounds.x/100), int(h*bounds.y/100)
            box = (left, top, min(w, max(left+1, round(w*(bounds.x+bounds.width)/100))),
                   min(h, max(top+1, round(h*(bounds.y+bounds.height)/100))))
            selected = io.BytesIO()
            normalized.crop(box).save(selected, 'PNG')
            data = selected.getvalue()
    except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError, ValidationError):
        raise HTTPException(422, "图片无效或超过 2000 万像素，请缩小后重试") from None
    try:
        async with httpx.AsyncClient(timeout=210, trust_env=False) as client:
            response = await client.post(f"{settings.trellis_url.rstrip('/')}/prepare-image", json={"image_base64": base64.b64encode(data).decode(), "model": model if isinstance(model,str) else 'isnet-anime'})
        if response.status_code != 200:
            raise HTTPException(503, "本机抠图服务繁忙或未就绪，请稍后重试，也可直接使用原图")
        result = response.content
        if normalized is not None and box is not None:
            # Return the original coordinate system so cropping and manual
            # restoration never drift relative to the source photograph.
            with Image.open(io.BytesIO(result)) as foreground:
                if foreground.size != (box[2]-box[0], box[3]-box[1]):
                    raise HTTPException(503, '抠图尺寸不一致，请重试')
                canvas = Image.new('RGBA', normalized.size, (0,0,0,0))
                canvas.paste(foreground.convert('RGBA'), box[:2])
            buffer = io.BytesIO();canvas.save(buffer, 'PNG');result = buffer.getvalue()
        return Response(result, media_type="image/png", headers={"Cache-Control": "private, no-store", 'X-Foreground-Model': response.headers.get('X-Foreground-Model',model if isinstance(model,str) else 'isnet-anime')})
    except httpx.HTTPError:
        raise HTTPException(503, "本机抠图暂时不可用，请检查生成服务") from None
