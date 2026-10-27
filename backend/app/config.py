from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr

class Settings(BaseSettings):
    app_env: str = "production"
    database_url: str
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"
    cors_origins: str = "http://localhost:8080"
    sql_echo: bool = False
    milvus_host: str = "milvus"
    milvus_port: int = 19530
    qwen2vl_url: str = "http://qwen2vl:8002"
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_proxy: str | None = None
    # Optional OpenAI-compatible or direct vision provider used by the
    # qwen2vl adapter. Leaving this unset makes the adapter fail explicitly,
    # instead of returning fabricated feature values.
    qwen2vl_provider_url: str | None = Field(default=None, validation_alias=AliasChoices("QWEN2VL_PROVIDER_URL", "ARK_API_URL"))
    qwen2vl_api_key: str | None = Field(default=None, validation_alias=AliasChoices("QWEN2VL_API_KEY", "ARK_API_KEY"))
    qwen2vl_model: str = Field(default="qwen-vl-max", validation_alias=AliasChoices("QWEN2VL_MODEL", "ARK_API_MODEL"))
    embedding_url: str | None = Field(default=None, validation_alias=AliasChoices("EMBEDDING_URL", "ARK_API_URL"))
    embedding_api_key: str | None = Field(default=None, validation_alias=AliasChoices("EMBEDDING_API_KEY", "ARK_API_KEY"))
    embedding_model: str = Field(default="text-embedding-3-large", validation_alias=AliasChoices("EMBEDDING_MODEL"))
    embedding_timeout: float = 30.0
    trellis_url: str = "http://trellis:8001"
    # Optional local-only, read-only bridge during rolling adapter upgrades.
    diagnostics_comfy_url: str = ""
    agent_http_timeout: float = 120.0
    vision_analysis_required: bool = True
    # 3D inference is substantially slower than metadata/analysis calls.
    # Keep its timeout independent so a long GPU run is not cut off by the
    # general agent HTTP timeout.
    generation_http_timeout: float = 1860.0
    generation_service_retries: int = 2
    generation_retry_backoff: float = 0.25
    trellis_model_path: str = "/models/trellis2"
    triposr_model_path: str = "/models/triposr"
    trellis_artifact_dir: str = "/artifacts"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin123"
    minio_bucket: str = "digital-human"
    minio_secure: bool = False
    upload_max_size_mb: int = 20
    jwt_secret: str = "change-this-jwt-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    alibaba_cloud_access_key_id: SecretStr = SecretStr("")
    alibaba_cloud_access_key_secret: SecretStr = SecretStr("")
    alibaba_sms_sign_name: str = ""
    alibaba_sms_template_code: str = ""
    alibaba_sms_region: str = "cn-hangzhou"
    alibaba_sms_scheme_name: str = ""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
