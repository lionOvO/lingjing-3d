"""SQLAlchemy 2.0 async ORM entities matching the MySQL schema exactly."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import BigInteger, Boolean, Enum as SqlEnum, Float, ForeignKey, Integer, String, Text, TIMESTAMP, func
from sqlalchemy import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


class ProjectType(str, Enum):
    ANIME_CHARACTER = "anime_character"
    OBJECT_MODEL = "object_model"


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerationTaskStatus(str, Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    RETRIEVING = "retrieving"
    GENERATING = "generating"
    EVALUATING = "evaluating"
    POSTPROCESSING = "postprocessing"
    COMPLETED = "completed"
    FAILED = "failed"


class OutputFormat(str, Enum):
    GLB = "glb"
    OBJ = "obj"
    FBX = "fbx"
    STL = "stl"


class RagEntryType(str, Enum):
    CHARACTER_STYLE = "character_style"
    GENERATION_PARAMS = "generation_params"
    MATERIAL_REFERENCE = "material_reference"


def EnumType(enum_class: type[Enum]) -> SqlEnum:
    """Persist enum values (the SQL schema literals), not Python member names."""
    return SqlEnum(enum_class, values_callable=lambda members: [member.value for member in members], native_enum=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    projects: Mapped[list[Project]] = relationship(back_populates="user")


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    project_type: Mapped[ProjectType] = mapped_column(EnumType(ProjectType), nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(EnumType(ProjectStatus), default=ProjectStatus.DRAFT, server_default=ProjectStatus.DRAFT.value, nullable=False)
    source_image_url: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="projects")
    tasks: Mapped[list[GenerationTask]] = relationship(back_populates="project")


class GenerationTask(TimestampMixin, Base):
    __tablename__ = "generation_tasks"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    task_type: Mapped[ProjectType] = mapped_column(EnumType(ProjectType), nullable=False)
    status: Mapped[GenerationTaskStatus] = mapped_column(EnumType(GenerationTaskStatus), default=GenerationTaskStatus.PENDING, server_default=GenerationTaskStatus.PENDING.value, nullable=False, index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(100))
    analysis_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    retrieved_params: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    generation_params: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    quality_score: Mapped[float | None] = mapped_column(Float)
    output_model_url: Mapped[str | None] = mapped_column(String(500))
    output_format: Mapped[OutputFormat] = mapped_column(EnumType(OutputFormat), default=OutputFormat.GLB, server_default=OutputFormat.GLB.value, nullable=False)
    texture_urls: Mapped[list[str] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)

    project: Mapped[Project] = relationship(back_populates="tasks")
    character_feature: Mapped[CharacterFeature | None] = relationship(back_populates="task", uselist=False)
    metadata_record: Mapped[ModelMetadata | None] = relationship(back_populates="task", uselist=False)


class StudioAsset(Base):
    """User-facing labels on an existing artifact; never changes the mesh."""
    __tablename__ = "studio_assets"
    task_id: Mapped[int] = mapped_column(ForeignKey("generation_tasks.id", ondelete="CASCADE"), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class StudioAssetTrash(Base):
    """Recoverable library deletion; artifacts and generation history stay intact."""
    __tablename__ = "studio_asset_trash"
    task_id: Mapped[int] = mapped_column(ForeignKey("generation_tasks.id", ondelete="CASCADE"), primary_key=True)
    deleted_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)


class AccountProfile(Base):
    __tablename__ = "account_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ModelRevision(TimestampMixin, Base):
    __tablename__ = "model_revisions"
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("generation_tasks.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    object_name: Mapped[str] = mapped_column(String(500), nullable=False)
    report: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    options: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ModelInspection(Base):
    __tablename__ = "model_inspections"
    task_id: Mapped[int] = mapped_column(ForeignKey("generation_tasks.id", ondelete="CASCADE"), primary_key=True)
    report: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    review: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class GenerationPreset(TimestampMixin, Base):
    __tablename__ = "generation_presets"
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    project_type: Mapped[str] = mapped_column(String(30), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CharacterFeature(Base):
    __tablename__ = "character_features"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("generation_tasks.id"), nullable=False)
    character_type: Mapped[str | None] = mapped_column(String(50))
    gender: Mapped[str | None] = mapped_column(String(20))
    hair_color: Mapped[str | None] = mapped_column(String(50))
    hair_style: Mapped[str | None] = mapped_column(String(100))
    eye_color: Mapped[str | None] = mapped_column(String(50))
    outfit_description: Mapped[str | None] = mapped_column(Text)
    pose: Mapped[str | None] = mapped_column(String(50))
    style_tags: Mapped[list[str] | None] = mapped_column(JSON)
    feature_vector_id: Mapped[str | None] = mapped_column(String(100))

    task: Mapped[GenerationTask] = relationship(back_populates="character_feature")


class ModelMetadata(Base):
    __tablename__ = "model_metadata"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("generation_tasks.id"), nullable=False)
    vertex_count: Mapped[int | None] = mapped_column(Integer)
    face_count: Mapped[int | None] = mapped_column(Integer)
    texture_resolution: Mapped[str | None] = mapped_column(String(20))
    has_pbr: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    file_size_mb: Mapped[float | None] = mapped_column(Float)
    bounding_box: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    task: Mapped[GenerationTask] = relationship(back_populates="metadata_record")


class RagKnowledgeEntry(TimestampMixin, Base):
    __tablename__ = "rag_knowledge_entries"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    collection_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    milvus_id: Mapped[str] = mapped_column(String(100), nullable=False)
    entry_type: Mapped[RagEntryType] = mapped_column(EnumType(RagEntryType), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str] | None] = mapped_column(JSON)
    source: Mapped[str | None] = mapped_column(String(200))
    usage_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    avg_quality_score: Mapped[float | None] = mapped_column(Float)
