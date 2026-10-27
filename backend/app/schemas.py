"""Pydantic v2 request and response contracts for persistence APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

from .models import GenerationTaskStatus, OutputFormat, ProjectStatus, ProjectType, RagEntryType


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=False, str_strip_whitespace=True)


class HairFeatures(APIModel):
    """Normalized hair attributes extracted from a reference image."""

    color: str = Field(default="unknown", min_length=1, max_length=50)
    style: str = Field(default="unknown", min_length=1, max_length=100)
    length: str = Field(default="unknown", min_length=1, max_length=30)


class FaceFeatures(APIModel):
    """Normalized facial attributes. Unknown is preferred to guessing."""

    eye_color: str = Field(default="unknown", min_length=1, max_length=50)
    expression: str = Field(default="unknown", min_length=1, max_length=50)
    shape: str = Field(default="unknown", min_length=1, max_length=50)


class OutfitFeatures(APIModel):
    """Normalized clothing attributes used by retrieval and generation."""

    category: str = Field(default="unknown", min_length=1, max_length=80)
    top: str = Field(default="unknown", min_length=1, max_length=120)
    bottom: str = Field(default="unknown", min_length=1, max_length=120)
    description: str = Field(default="unknown", min_length=1, max_length=500)
    accessories: list[str] = Field(default_factory=list, max_length=30)


class CharacterFeatureExtraction(APIModel):
    """Raw/normalized-compatible contract returned by the vision adapter."""

    character_type: str = Field(default="unknown", min_length=1, max_length=50)
    gender: str = Field(default="unknown", min_length=1, max_length=20)
    hair: HairFeatures = Field(default_factory=HairFeatures)
    face: FaceFeatures = Field(default_factory=FaceFeatures)
    outfit: OutfitFeatures = Field(default_factory=OutfitFeatures)
    pose: str = Field(default="unknown", min_length=1, max_length=50)
    style_tags: list[str] = Field(default_factory=list, max_length=50)


class NormalizedCharacterFeatures(CharacterFeatureExtraction):
    """Canonical feature document persisted to MySQL and indexed in Milvus."""

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    uncertain_fields: list[str] = Field(default_factory=list, max_length=50)
    source: str = Field(default="qwen2-vl", min_length=1, max_length=100)
    raw_analysis: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(APIModel):
    status: str


class MessageResponse(APIModel):
    message: str


class AuthRegister(APIModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True, extra="forbid")
    phone: str = Field(pattern=r"^1[3-9][0-9]{9}$")
    code: str = Field(pattern=r"^[0-9]{6}$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    avatar_url: HttpUrl | None = None


class AuthLogin(APIModel):
    username_or_email: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(APIModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(APIModel):
    refresh_token: str = Field(min_length=20)


class UserCreate(APIModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    email: EmailStr
    password_hash: str = Field(min_length=8, max_length=255)
    avatar_url: HttpUrl | None = None


class UserRead(APIModel):
    id: int
    username: str
    email: EmailStr
    avatar_url: str | None
    created_at: datetime
    updated_at: datetime
    display_name: str = ""


class ProjectCreate(APIModel):
    user_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    project_type: ProjectType
    source_image_url: HttpUrl | None = None


class ProjectUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: ProjectStatus | None = None
    source_image_url: HttpUrl | None = None


class ProjectRead(APIModel):
    id: int
    user_id: int
    name: str
    description: str | None
    project_type: ProjectType
    status: ProjectStatus
    source_image_url: str | None
    created_at: datetime
    updated_at: datetime


class TaskCreate(APIModel):
    project_id: int = Field(gt=0)
    task_type: ProjectType
    generation_params: dict[str, Any] | None = None
    output_format: OutputFormat = OutputFormat.GLB
    source_image_url: HttpUrl | None = None


class UploadResponse(APIModel):
    url: str
    object_name: str
    filename: str
    content_type: str
    size: int = Field(ge=1)
    task_id: int | None = None


class UploadUrlRequest(APIModel):
    url: HttpUrl


class TaskUpdate(APIModel):
    status: GenerationTaskStatus | None = None
    analysis_result: dict[str, Any] | None = None
    retrieved_params: dict[str, Any] | None = None
    generation_params: dict[str, Any] | None = None
    quality_score: float | None = Field(default=None, ge=0, le=1)
    output_model_url: HttpUrl | None = None
    output_format: OutputFormat | None = None
    texture_urls: list[HttpUrl] | None = None
    error_message: str | None = None


class TaskRead(APIModel):
    id: int
    project_id: int
    task_type: ProjectType
    status: GenerationTaskStatus
    celery_task_id: str | None
    analysis_result: dict[str, Any] | None
    retrieved_params: dict[str, Any] | None
    generation_params: dict[str, Any] | None
    quality_score: float | None
    output_model_url: str | None
    output_format: OutputFormat
    texture_urls: list[str] | None
    error_message: str | None
    retry_count: int
    created_at: datetime
    completed_at: datetime | None


class CharacterFeatureUpsert(APIModel):
    character_type: str | None = Field(default=None, max_length=50)
    gender: str | None = Field(default=None, max_length=20)
    hair_color: str | None = Field(default=None, max_length=50)
    hair_style: str | None = Field(default=None, max_length=100)
    eye_color: str | None = Field(default=None, max_length=50)
    outfit_description: str | None = None
    pose: str | None = Field(default=None, max_length=50)
    style_tags: list[str] | None = None
    feature_vector_id: str | None = Field(default=None, max_length=100)


class CharacterFeatureRead(CharacterFeatureUpsert):
    id: int
    task_id: int


class ModelMetadataUpsert(APIModel):
    vertex_count: int | None = Field(default=None, ge=0)
    face_count: int | None = Field(default=None, ge=0)
    texture_resolution: str | None = Field(default=None, max_length=20)
    has_pbr: bool = False
    file_size_mb: float | None = Field(default=None, ge=0)
    bounding_box: dict[str, Any] | None = None


class ModelMetadataRead(ModelMetadataUpsert):
    id: int
    task_id: int


class ModelDownloadResponse(APIModel):
    task_id: int
    download_url: str
    output_format: OutputFormat


class ModelConvertRequest(APIModel):
    output_format: OutputFormat


class RagSearchQuery(APIModel):
    query: str = Field(min_length=1, max_length=2000)
    collection_name: str | None = Field(default=None, min_length=1, max_length=100)
    offset: int = Field(default=0, ge=0)
    top_k: int = Field(default=5, ge=1, le=50)


class RagFeedback(APIModel):
    entry_id: int = Field(gt=0)
    quality_score: float = Field(ge=0, le=1)
    helpful: bool = True


class AgentInvokeRequest(APIModel):
    task_id: int = Field(gt=0)
    input: dict[str, Any] = Field(default_factory=dict)


class AgentWorkflowResponse(APIModel):
    task_id: int
    status: str
    state: dict[str, Any] = Field(default_factory=dict)


class RagEntryCreate(APIModel):
    collection_name: str = Field(min_length=1, max_length=100)
    milvus_id: str = Field(min_length=1, max_length=100)
    entry_type: RagEntryType
    title: str = Field(min_length=1, max_length=200)
    content: str | None = None
    tags: list[str] | None = None
    source: str | None = Field(default=None, max_length=200)
    avg_quality_score: float | None = Field(default=None, ge=0, le=1)


class RagEntryRead(RagEntryCreate):
    id: int
    usage_count: int
    created_at: datetime
