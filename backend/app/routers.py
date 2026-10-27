"""Persistence-backed REST endpoints for the database-backed modules."""

import asyncio
from datetime import datetime, timezone
import json
import logging
import httpx

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .database import SessionLocal, get_db_session
from .exceptions import NotFoundError
from .config import settings
from .models import CharacterFeature, GenerationTask, GenerationTaskStatus, ModelMetadata, Project, ProjectStatus, User, RagKnowledgeEntry, RagEntryType, AccountProfile
from .schemas import (AgentInvokeRequest, AgentWorkflowResponse, AuthLogin, AuthRegister, CharacterFeatureRead, CharacterFeatureUpsert,
                      ModelConvertRequest, ModelDownloadResponse, ModelMetadataRead, ModelMetadataUpsert, ProjectCreate, ProjectRead, ProjectUpdate,
                      RagEntryCreate, RagEntryRead, RagFeedback, RagSearchQuery, RefreshRequest, TaskCreate, TaskRead, TaskUpdate, TokenResponse, UploadResponse, UploadUrlRequest, UserCreate, UserRead)
from .security import create_access_token, create_refresh_token, decode_refresh_token, get_current_user, hash_password, verify_password, account_version, validate_token_version
from .agents import workflow
from .worker import _fallback_model, generate_3d
from .storage import StorageError, storage, safe_filename
from .artifact_metadata import glb_statistics
from .reference_tools import validate_generation_reference

logger = logging.getLogger("digital_human.api")
router = APIRouter(prefix="/api/v1")


@router.get("/generation/capabilities")
async def generation_capabilities():
    try:
        async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
            response = await client.get(f"{settings.trellis_url.rstrip('/')}/capabilities")
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise HTTPException(status_code=503, detail="生成服务尚未就绪，请确认本机 ComfyUI 和生成服务已启动") from error


@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: AuthLogin, db: AsyncSession = Depends(get_db_session)):
    identifier = payload.username_or_email.strip()
    user = await db.scalar(select(User).where((User.username == identifier) | (User.email == identifier)))
    if not user or not verify_password(payload.password, user.password_hash):
        logger.warning("Failed login for identifier=%s", identifier)
        raise HTTPException(status_code=401, detail="账号或密码错误")
    version = await account_version(db, user.id)
    return TokenResponse(
        access_token=create_access_token(user.id, version),
        refresh_token=create_refresh_token(user.id, version),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db_session)):
    user_id = decode_refresh_token(payload.refresh_token)
    if not await db.get(User, user_id):
        raise HTTPException(status_code=401, detail="用户不存在或已被删除")
    version = await account_version(db, user_id)
    validate_token_version(payload.refresh_token, version)
    return TokenResponse(access_token=create_access_token(user_id, version), refresh_token=create_refresh_token(user_id, version), expires_in=settings.access_token_expire_minutes * 60)


@router.get("/auth/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    profile = await db.get(AccountProfile, current_user.id)
    return {**UserRead.model_validate(current_user).model_dump(), "display_name": profile.display_name if profile else ""}


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db_session)):
    # The original foundation endpoint accepted arbitrary password hashes and
    # would bypass verified registration. Existing accounts are unaffected.
    raise HTTPException(status_code=410, detail="请通过手机号验证码注册账号")


@router.get("/users/{user_id}", response_model=UserRead)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db_session)):
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError("User", user_id)
    return user


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db_session)):
    if not await db.get(User, payload.user_id):
        raise NotFoundError("User", payload.user_id)
    project = Project(user_id=payload.user_id, name=payload.name, description=payload.description, project_type=payload.project_type, source_image_url=str(payload.source_image_url) if payload.source_image_url else None)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    logger.info("Created project id=%s", project.id)
    return project


@router.get("/projects", response_model=list[ProjectRead])
async def list_projects(user_id: int | None = Query(default=None, gt=0), offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db_session)):
    query = select(Project).order_by(Project.created_at.desc()).offset(offset).limit(limit)
    if user_id:
        query = query.where(Project.user_id == user_id)
    return list((await db.scalars(query)).all())


@router.get("/projects/{project_id}", response_model=ProjectRead)
async def get_project(project_id: int, db: AsyncSession = Depends(get_db_session)):
    project = await db.get(Project, project_id)
    if not project:
        raise NotFoundError("Project", project_id)
    return project


@router.get("/projects/{project_id}/tasks", response_model=list[TaskRead])
async def list_project_tasks(project_id: int, db: AsyncSession = Depends(get_db_session)):
    """Return a project's generation history, newest task first.

    The project page uses this authoritative association to reopen completed
    models.  It deliberately does not infer a task from the browser's global
    "recent task" cache, which can belong to another project.
    """
    if not await db.get(Project, project_id):
        raise NotFoundError("Project", project_id)
    query = (
        select(GenerationTask)
        .where(GenerationTask.project_id == project_id)
        .order_by(GenerationTask.created_at.desc(), GenerationTask.id.desc())
    )
    tasks = list((await db.scalars(query)).all())
    logger.info("Listed project generation tasks project_id=%s count=%s", project_id, len(tasks))
    return tasks


@router.get("/projects/{project_id}/source-image")
async def get_project_source_image(project_id: int, db: AsyncSession = Depends(get_db_session)):
    """Serve a project's stored source image through the API gateway.

    Browsers cannot resolve the internal ``minio`` hostname from a presigned
    URL returned inside Docker.  Only objects belonging to this project's
    stored MinIO URL are served; external URLs are intentionally rejected.
    """
    project = await db.get(Project, project_id)
    if not project or not project.source_image_url:
        raise NotFoundError("Project source image", project_id)
    object_name = storage.object_name_from_url(project.source_image_url)
    if not object_name:
        raise NotFoundError("Project source image", project_id)
    try:
        data, content_type = await storage.get_object(object_name)
    except StorageError as exc:
        logger.warning("Project source image unavailable project_id=%s object=%s", project_id, object_name)
        raise HTTPException(status_code=404, detail="参考图暂时无法读取") from exc
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=300"})


@router.patch("/projects/{project_id}", response_model=ProjectRead)
@router.put("/projects/{project_id}", response_model=ProjectRead)
async def update_project(project_id: int, payload: ProjectUpdate, db: AsyncSession = Depends(get_db_session)):
    project = await db.get(Project, project_id)
    if not project:
        raise NotFoundError("Project", project_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "status" and value is None:
            continue
        setattr(project, key, str(value) if key == "source_image_url" and value else value)
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db_session)):
    # Lock the project row while collecting dependent task ids. This prevents
    # a concurrent task update from reintroducing a foreign-key reference
    # between the cleanup statements and the final project delete.
    project = await db.scalar(select(Project).where(Project.id == project_id).with_for_update())
    if not project:
        raise NotFoundError("Project", project_id)
    # Project tasks do not use database-level ON DELETE CASCADE. Remove the
    # dependent rows explicitly so deleting a project also works after a
    # generation task has been created.
    task_ids = list((await db.scalars(select(GenerationTask.id).where(GenerationTask.project_id == project_id))).all())
    try:
        if task_ids:
            await db.execute(delete(CharacterFeature).where(CharacterFeature.task_id.in_(task_ids)))
            await db.execute(delete(ModelMetadata).where(ModelMetadata.task_id.in_(task_ids)))
            await db.execute(delete(GenerationTask).where(GenerationTask.id.in_(task_ids)))
        await db.delete(project)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        logger.exception("Project deletion blocked by an integrity constraint id=%s", project_id, exc_info=exc)
        raise HTTPException(status_code=409, detail="项目仍有相关数据未清理，暂时无法删除，请稍后重试") from exc
    logger.info("Deleted project id=%s tasks=%s", project_id, len(task_ids))


@router.post("/uploads", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_image(image: UploadFile = File(...)):
    """Upload a source image to MinIO without creating a generation task."""
    try:
        stored = await storage.upload_image(image)
    except StorageError as exc:
        logger.warning("Image upload rejected filename=%s reason=%s", image.filename, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UploadResponse(url=stored.url, object_name=stored.object_name, filename=safe_filename(image.filename or "upload"), content_type=stored.content_type, size=stored.size)


@router.post("/uploads/url", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_image_url(payload: UploadUrlRequest):
    try:
        stored = await storage.upload_url(str(payload.url))
    except StorageError as exc:
        logger.warning("Remote image upload rejected url=%s reason=%s", payload.url, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UploadResponse(url=stored.url, object_name=stored.object_name, filename=safe_filename(str(payload.url).rsplit("/", 1)[-1]), content_type=stored.content_type, size=stored.size)


@router.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(request: Request, db: AsyncSession = Depends(get_db_session)):
    """Accept JSON task requests and the documented multipart image upload."""
    source_filename: str | None = None
    source_url: str | None = None
    stored_object_name: str | None = None
    try:
        if request.headers.get("content-type", "").startswith("multipart/form-data"):
            form = await request.form()
            source_file = form.get("image")
            if source_file is None or not hasattr(source_file, "read"):
                raise ValueError("multipart request must include an image file")
            source_filename = getattr(source_file, "filename", None)
            raw_params = form.get("generation_params")
            parsed_params = json.loads(raw_params) if isinstance(raw_params, str) and raw_params else None
            payload = TaskCreate.model_validate({
                "project_id": form.get("project_id"),
                "task_type": form.get("task_type", "anime_character"),
                "generation_params": parsed_params,
                "output_format": form.get("output_format", "glb"),
            })
            stored = await storage.upload_image(source_file, prefix=f"projects/{payload.project_id}")
            source_url = stored.url
            stored_object_name = stored.object_name
        else:
            payload = TaskCreate.model_validate(await request.json())
            source_url = str(payload.source_image_url) if payload.source_image_url else None
    except (ValidationError, ValueError) as exc:
        detail = exc.errors() if isinstance(exc, ValidationError) else "Invalid request payload"
        raise HTTPException(status_code=422, detail=detail) from exc
    except StorageError as exc:
        logger.warning("Task image upload failed filename=%s reason=%s", source_filename, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    project = await db.get(Project, payload.project_id)
    if not project:
        if stored_object_name:
            await storage.delete(stored_object_name)
        raise NotFoundError("Project", payload.project_id)
    generation_params = dict(payload.generation_params or {})
    source_object = stored_object_name or (storage.object_name_from_url(source_url) if source_url else None)
    if generation_params.get('input_preprocessed'):
        if not source_object:
            raise HTTPException(422, '请先上传已确认的参考图片')
        try:
            actual, _ = await storage.get_object(source_object)
            original_name = generation_params.get('_original_source_object_name')
            original = (await storage.get_object(original_name))[0] if original_name and original_name != source_object else None
            preparation = generation_params.get('image_preparation') or {}
            accepted = isinstance(preparation, dict) and preparation.get('background_risk_accepted') is True
            generation_params['_input_validation'] = await asyncio.to_thread(validate_generation_reference, actual, original, accepted)
        except (ValueError, StorageError) as exc:
            raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else '输入图片暂时无法校验，请重新上传') from None
    if source_url:
        project.source_image_url = source_url
    if source_object:
        generation_params["_source_object_name"] = source_object
    task = GenerationTask(project_id=payload.project_id, task_type=payload.task_type, generation_params=generation_params, output_format=payload.output_format)
    project.status = ProjectStatus.PROCESSING
    db.add(task)
    await db.commit()
    await db.refresh(task)
    if source_url:
        try:
            job = generate_3d.delay(str(task.id), source_url)
            task.celery_task_id = job.id
            await db.commit()
            await db.refresh(task)
            logger.info("Generation task queued task_id=%s celery_id=%s", task.id, job.id)
        except Exception as exc:
            logger.exception("Could not enqueue generation task id=%s", task.id)
            task.status = GenerationTaskStatus.FAILED
            task.error_message = f"Task queue unavailable: {exc}"
            project.status = ProjectStatus.FAILED
            await db.commit()
    return task


@router.get("/tasks/{task_id}", response_model=TaskRead)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db_session)):
    task = await db.get(GenerationTask, task_id)
    if not task:
        raise NotFoundError("Task", task_id)
    return task


@router.patch("/tasks/{task_id}", response_model=TaskRead)
async def update_task(task_id: int, payload: TaskUpdate, db: AsyncSession = Depends(get_db_session)):
    task = await db.get(GenerationTask, task_id)
    if not task:
        raise NotFoundError("Task", task_id)
    project = await db.get(Project, task.project_id)
    values = {key: value for key, value in payload.model_dump(exclude_unset=True).items() if not (key == "status" and value is None)}
    if "output_model_url" in values and values["output_model_url"]:
        values["output_model_url"] = str(values["output_model_url"])
    if "texture_urls" in values and values["texture_urls"]:
        values["texture_urls"] = [str(url) for url in values["texture_urls"]]
    for key, value in values.items():
        setattr(task, key, value)
    if task.status == GenerationTaskStatus.COMPLETED:
        task.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if project:
            project.status = ProjectStatus.COMPLETED
    elif task.status == GenerationTaskStatus.FAILED and project:
        project.status = ProjectStatus.FAILED
    await db.commit()
    await db.refresh(task)
    return task


@router.put("/tasks/{task_id}/character-features", response_model=CharacterFeatureRead)
async def upsert_character_features(task_id: int, payload: CharacterFeatureUpsert, db: AsyncSession = Depends(get_db_session)):
    if not await db.get(GenerationTask, task_id):
        raise NotFoundError("Task", task_id)
    feature = await db.scalar(select(CharacterFeature).where(CharacterFeature.task_id == task_id))
    if feature is None:
        feature = CharacterFeature(task_id=task_id)
        db.add(feature)
    for key, value in payload.model_dump().items():
        setattr(feature, key, value)
    await db.commit()
    await db.refresh(feature)
    return feature


@router.get("/tasks/{task_id}/character-features", response_model=CharacterFeatureRead)
async def get_character_features(task_id: int, db: AsyncSession = Depends(get_db_session)):
    feature = await db.scalar(select(CharacterFeature).where(CharacterFeature.task_id == task_id))
    if feature is None:
        raise NotFoundError("Character features for task", task_id)
    return feature


@router.put("/tasks/{task_id}/metadata", response_model=ModelMetadataRead)
async def upsert_model_metadata(task_id: int, payload: ModelMetadataUpsert, db: AsyncSession = Depends(get_db_session)):
    if not await db.get(GenerationTask, task_id):
        raise NotFoundError("Task", task_id)
    metadata = await db.scalar(select(ModelMetadata).where(ModelMetadata.task_id == task_id))
    if metadata is None:
        metadata = ModelMetadata(task_id=task_id)
        db.add(metadata)
    for key, value in payload.model_dump().items():
        setattr(metadata, key, value)
    await db.commit()
    await db.refresh(metadata)
    return metadata


@router.get("/tasks/{task_id}/metadata", response_model=ModelMetadataRead)
async def get_model_metadata(task_id: int, db: AsyncSession = Depends(get_db_session)):
    metadata = await db.scalar(select(ModelMetadata).where(ModelMetadata.task_id == task_id))
    if metadata is None:
        raise NotFoundError("Model metadata for task", task_id)
    if metadata.vertex_count is None or metadata.file_size_mb is None:
        task = await db.get(GenerationTask, task_id)
        object_name = (task.generation_params or {}).get('_artifact_object_name') if task else None
        if object_name and task.output_format.value == 'glb':
            try:
                data, _ = await storage.get_object(str(object_name))
                stats = glb_statistics(data)
                # Enrich older records in the response without changing stored
                # task history or substituting a generated artifact.
                return ModelMetadataRead.model_validate(metadata).model_copy(update={
                    key: value for key, value in stats.items() if getattr(metadata, key) is None
                })
            except (StorageError, ValueError, KeyError, IndexError):
                logger.warning('Unable to read GLB statistics task_id=%s', task_id, exc_info=True)
    return metadata


@router.post("/tasks/{task_id}/retry", response_model=TaskRead)
async def retry_task(task_id: int, db: AsyncSession = Depends(get_db_session)):
    task = await db.get(GenerationTask, task_id)
    if not task:
        raise NotFoundError("Task", task_id)
    if task.status != GenerationTaskStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only failed tasks can be retried")
    task.status = GenerationTaskStatus.PENDING
    task.retry_count += 1
    task.error_message = None
    project = await db.get(Project, task.project_id)
    await db.commit()
    await db.refresh(task)
    source_url = project.source_image_url if project else None
    if source_url:
        try:
            job = generate_3d.delay(str(task.id), source_url)
            task.celery_task_id = job.id
            await db.commit()
        except Exception as exc:
            task.status = GenerationTaskStatus.FAILED
            task.error_message = f"Task queue unavailable: {exc}"
            if project:
                project.status = ProjectStatus.FAILED
            await db.commit()
            logger.exception("Could not enqueue retry task id=%s", task.id)
    logger.info("Retry requested for task id=%s retry_count=%s", task.id, task.retry_count)
    return task


@router.delete("/tasks/{task_id}", response_model=TaskRead)
async def cancel_task(task_id: int, db: AsyncSession = Depends(get_db_session)):
    task = await db.get(GenerationTask, task_id)
    if not task:
        raise NotFoundError("Task", task_id)
    if task.status in (GenerationTaskStatus.COMPLETED, GenerationTaskStatus.FAILED):
        raise HTTPException(status_code=409, detail="Task is no longer cancellable")
    project = await db.get(Project, task.project_id)
    task.status = GenerationTaskStatus.FAILED
    task.error_message = "Task cancelled by user"
    if project:
        project.status = ProjectStatus.FAILED
    if task.celery_task_id:
        try:
            generate_3d.app.control.revoke(task.celery_task_id, terminate=False)
        except Exception:
            logger.warning("Could not revoke celery task id=%s", task.celery_task_id, exc_info=True)
    await db.commit()
    await db.refresh(task)
    return task


@router.websocket("/tasks/{task_id}/progress")
async def task_progress(websocket: WebSocket, task_id: int):
    await websocket.accept()
    try:
        await _single_progress(websocket, task_id)
    except WebSocketDisconnect:
        logger.info("Progress websocket disconnected task_id=%s", task_id)


async def _single_progress(websocket: WebSocket, task_id: int):
    """Stream persisted task state until the workflow reaches a terminal state.

    Celery owns execution while FastAPI owns browser sockets, so the socket
    reads the persisted task record rather than depending on worker-local
    memory. This also remains correct across an API container restart.
    """
    progress_by_status = {
        GenerationTaskStatus.PENDING: 0,
        GenerationTaskStatus.ANALYZING: 15,
        GenerationTaskStatus.RETRIEVING: 35,
        GenerationTaskStatus.GENERATING: 60,
        GenerationTaskStatus.EVALUATING: 82,
        GenerationTaskStatus.POSTPROCESSING: 94,
        GenerationTaskStatus.COMPLETED: 100,
        GenerationTaskStatus.FAILED: 0,
    }
    previous: tuple[str, int, str | None] | None = None
    while True:
        async with SessionLocal() as session:
            task = await session.get(GenerationTask, task_id)
        if task is None:
            await websocket.send_json({"task_id": task_id, "status": "failed", "progress": 0, "error_message": "任务不存在"})
            await websocket.close(code=1008)
            return
        status_value = task.status.value
        progress = progress_by_status[task.status]
        snapshot = (status_value, progress, task.error_message)
        if snapshot != previous:
            await websocket.send_json({
                "task_id": task.id,
                "status": status_value,
                "progress": progress,
                "error_message": task.error_message,
            })
            previous = snapshot
        if task.status in (GenerationTaskStatus.COMPLETED, GenerationTaskStatus.FAILED):
            await websocket.close()
            return
        await asyncio.sleep(1)


@router.get("/models/{task_id}", response_model=ModelMetadataRead)
async def model_metadata(task_id: int, db: AsyncSession = Depends(get_db_session)):
    return await get_model_metadata(task_id, db)


async def _ensure_model_artifact(task: GenerationTask, db: AsyncSession) -> str | None:
    """Materialize legacy ``mock://`` results for browser/API consumers.

    Older completed tasks may have been persisted before the worker started
    uploading its fallback artifact. Keep the compatibility work at the
    delivery boundary so those tasks become usable without being re-run.
    Real engine URLs and already materialized objects are left untouched.
    """
    params = dict(task.generation_params or {})
    object_name = params.get("_artifact_object_name")
    if object_name:
        return str(object_name)
    if not str(task.output_model_url or "").startswith("mock://"):
        return None
    try:
        object_name = await storage.upload_generated_model(
            task.id,
            _fallback_model(task.output_format.value),
            task.output_format.value,
        )
    except StorageError as exc:
        logger.warning("Legacy mock model materialization failed task_id=%s", task.id, exc_info=True)
        raise HTTPException(status_code=503, detail="生成模型暂时不可用，请稍后重试") from exc
    except Exception as exc:
        logger.exception("Unexpected legacy mock model materialization error task_id=%s", task.id)
        raise HTTPException(status_code=503, detail="生成模型暂时不可用，请稍后重试") from exc
    params["_artifact_object_name"] = object_name
    task.generation_params = params
    task.output_model_url = f"/api/v1/models/{task.id}/content"
    await db.commit()
    logger.info("Materialized legacy mock model task_id=%s object=%s", task.id, object_name)
    return str(object_name)


@router.get("/models/{task_id}/download", response_model=ModelDownloadResponse)
async def download_model(task_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    task = await db.get(GenerationTask, task_id)
    if not task:
        raise NotFoundError("Task", task_id)
    if not task.output_model_url:
        raise HTTPException(status_code=404, detail="Generated model is not available")
    await _ensure_model_artifact(task, db)
    download_url = task.output_model_url
    if (task.generation_params or {}).get("_artifact_object_name"):
        download_url = f"{request.url_for('model_content', task_id=str(task.id))}?download=true"
    return ModelDownloadResponse(task_id=task.id, download_url=download_url, output_format=task.output_format)


@router.get("/models/{task_id}/content", name="model_content")
async def model_content(task_id: int, download: bool = Query(default=False), db: AsyncSession = Depends(get_db_session)):
    """Stream generated artifacts through the API, keeping MinIO private."""
    task = await db.get(GenerationTask, task_id)
    if not task:
        raise NotFoundError("Task", task_id)
    object_name = (task.generation_params or {}).get("_artifact_object_name")
    if not object_name:
        object_name = await _ensure_model_artifact(task, db)
    if not object_name:
        raise HTTPException(status_code=404, detail="生成模型尚不可用")
    try:
        data, content_type = await storage.get_object(str(object_name))
    except StorageError as exc:
        logger.warning("Generated model content unavailable task_id=%s", task_id, exc_info=True)
        raise HTTPException(status_code=404, detail="生成模型文件暂不可用") from exc
    headers = {"Cache-Control": "private, max-age=300"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="moonlit-model-{task.id}.{task.output_format.value}"'
    return Response(content=data, media_type=content_type, headers=headers)


@router.get("/models/{task_id}/preview", response_model=ModelDownloadResponse)
async def preview_model(task_id: int, request: Request, db: AsyncSession = Depends(get_db_session)):
    task = await db.get(GenerationTask, task_id)
    if not task:
        raise NotFoundError("Task", task_id)
    if not task.output_model_url:
        raise HTTPException(status_code=404, detail="Generated model is not available")
    await _ensure_model_artifact(task, db)
    preview_url = task.output_model_url
    if (task.generation_params or {}).get("_artifact_object_name"):
        preview_url = str(request.url_for("model_content", task_id=str(task.id)))
    return ModelDownloadResponse(task_id=task.id, download_url=preview_url, output_format=task.output_format)


@router.post("/models/{task_id}/convert", response_model=TaskRead)
async def convert_model(task_id: int, payload: ModelConvertRequest, db: AsyncSession = Depends(get_db_session)):
    task = await db.get(GenerationTask, task_id)
    if not task:
        raise NotFoundError("Task", task_id)
    if not task.output_model_url:
        raise HTTPException(status_code=409, detail="Generated model is not available")
    task.output_format = payload.output_format
    await db.commit()
    await db.refresh(task)
    return task


@router.post("/rag/entries", response_model=RagEntryRead, status_code=status.HTTP_201_CREATED)
async def create_rag_entry(payload: RagEntryCreate, db: AsyncSession = Depends(get_db_session)):
    entry = RagKnowledgeEntry(**payload.model_dump())
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.get("/rag/entries", response_model=list[RagEntryRead])
async def list_rag_entries(response: Response, collection_name: str | None = None, entry_type: RagEntryType | None = None, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db_session)):
    filters = []
    if collection_name:
        filters.append(RagKnowledgeEntry.collection_name == collection_name)
    if entry_type:
        filters.append(RagKnowledgeEntry.entry_type == entry_type)
    total = await db.scalar(select(func.count()).select_from(RagKnowledgeEntry).where(*filters))
    query = select(RagKnowledgeEntry).where(*filters).order_by(RagKnowledgeEntry.created_at.desc()).offset(offset).limit(limit)
    response.headers["X-Total-Count"] = str(total or 0)
    return list((await db.scalars(query)).all())


@router.get("/rag/search", response_model=list[RagEntryRead])
async def search_rag(response: Response, query: RagSearchQuery = Depends(), db: AsyncSession = Depends(get_db_session)):
    """Search all knowledge by default, or limit results to one collection."""
    pattern = f"%{query.query}%"
    filters = [RagKnowledgeEntry.title.ilike(pattern) | RagKnowledgeEntry.content.ilike(pattern)]
    if query.collection_name:
        filters.append(RagKnowledgeEntry.collection_name == query.collection_name)
    total = await db.scalar(select(func.count()).select_from(RagKnowledgeEntry).where(*filters))
    statement = select(RagKnowledgeEntry).where(*filters).order_by(RagKnowledgeEntry.created_at.desc()).offset(query.offset).limit(query.top_k)
    response.headers["X-Total-Count"] = str(total or 0)
    return list((await db.scalars(statement)).all())


@router.post("/rag/feedback", response_model=RagEntryRead)
async def rag_feedback(payload: RagFeedback, db: AsyncSession = Depends(get_db_session)):
    entry = await db.get(RagKnowledgeEntry, payload.entry_id)
    if not entry:
        raise NotFoundError("RAG entry", payload.entry_id)
    previous_count = entry.usage_count
    previous_average = entry.avg_quality_score or 0.0
    entry.usage_count = previous_count + 1
    entry.avg_quality_score = ((previous_average * previous_count) + payload.quality_score) / entry.usage_count
    await db.commit()
    await db.refresh(entry)
    return entry


@router.get("/rag/styles", response_model=list[RagEntryRead])
async def rag_styles(db: AsyncSession = Depends(get_db_session)):
    return list((await db.scalars(select(RagKnowledgeEntry).where(RagKnowledgeEntry.entry_type == RagEntryType.CHARACTER_STYLE))).all())


@router.get("/rag/materials", response_model=list[RagEntryRead])
async def rag_materials(db: AsyncSession = Depends(get_db_session)):
    return list((await db.scalars(select(RagKnowledgeEntry).where(RagKnowledgeEntry.entry_type == RagEntryType.MATERIAL_REFERENCE))).all())


@router.get("/agents/workflow/{task_id}", response_model=AgentWorkflowResponse)
async def agent_workflow(task_id: int, db: AsyncSession = Depends(get_db_session)):
    task = await db.get(GenerationTask, task_id)
    if not task:
        raise NotFoundError("Task", task_id)
    return AgentWorkflowResponse(task_id=task_id, status=task.status.value, state={
        "retry_count": task.retry_count,
        "quality_score": task.quality_score,
        "quality_checks": (task.retrieved_params or {}).get("quality_checks", {}),
        "quality_repair_suggestions": (task.retrieved_params or {}).get("quality_repair_suggestions", []),
        "quality_repair_sources": (task.retrieved_params or {}).get("quality_repair_sources", []),
        "quality_repair_degraded": bool((task.retrieved_params or {}).get("quality_repair_degraded", False)),
        "analysis_result": task.analysis_result,
        "retrieved_params": task.retrieved_params,
        "generation_params": task.generation_params,
        "generated_model_url": task.output_model_url,
        "generated_textures": task.texture_urls,
        "error_message": task.error_message,
    })


@router.post("/agents/invoke", response_model=AgentWorkflowResponse)
async def invoke_agent(payload: AgentInvokeRequest, db: AsyncSession = Depends(get_db_session)):
    task = await db.get(GenerationTask, payload.task_id)
    if not task:
        raise NotFoundError("Task", payload.task_id)
    project = await db.get(Project, task.project_id)
    state = await workflow.ainvoke({
        "task_id": str(payload.task_id),
        "project_id": task.project_id,
        "task_type": task.task_type.value,
        "source_image_url": (project.source_image_url if project else ""),
        "output_format": task.output_format.value,
        "generation_params": task.generation_params or {},
        "retry_count": task.retry_count,
        **payload.input,
    })
    task.status = GenerationTaskStatus(state.get("status", "failed")) if state.get("status") in {s.value for s in GenerationTaskStatus} else GenerationTaskStatus.FAILED
    task.analysis_result = state.get("character_features")
    task.retrieved_params = {
        "context": state.get("retrieved_context") or [],
        "sources": state.get("retrieval_sources") or [],
        "confidence": state.get("retrieval_confidence"),
        "degraded": bool(state.get("retrieval_degraded", False)),
        "query": state.get("retrieval_query"),
        "quality_checks": state.get("quality_checks") or {},
        "quality_repair_suggestions": state.get("quality_repair_suggestions") or [],
        "quality_repair_sources": state.get("quality_repair_sources") or [],
        "quality_repair_degraded": bool(state.get("quality_repair_degraded", False)),
    }
    task.generation_params = state.get("generation_params")
    task.quality_score = state.get("quality_score")
    task.output_model_url = state.get("generated_model_url")
    task.texture_urls = state.get("generated_textures")
    task.error_message = state.get("error_message")
    task.retry_count = int(state.get("retry_count", task.retry_count))
    if task.status == GenerationTaskStatus.COMPLETED:
        task.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if project:
            project.status = ProjectStatus.COMPLETED
    elif task.status == GenerationTaskStatus.FAILED and project:
        project.status = ProjectStatus.FAILED
    await db.commit()
    return AgentWorkflowResponse(task_id=payload.task_id, status=state.get("status", task.status.value), state=dict(state))
