from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Knowledge Base Agent Assistant"
    service_name: str = "backend-api"
    version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    backend_cors_origins: list[str] = ["http://localhost:5173"]
    database_url: str = "postgresql+psycopg://kb_agent:change-me@postgres:5432/kb_agent"
    jwt_secret_key: str = "dev-only-change-me-please-32-bytes-min"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    default_admin_email: str = "admin@example.local"
    default_admin_username: str = "admin"
    default_admin_password: str = "AdminPassword123"
    default_admin_display_name: str = "Administrator"
    default_consumer_email: str = "consumer@example.local"
    default_consumer_username: str = "consumer"
    default_consumer_display_name: str = "普通用户"
    login_failure_lock_threshold: int = 5
    login_lock_minutes: int = 15
    max_file_size_mb: int = 50
    max_batch_upload_count: int = 50
    minio_endpoint: str = "http://minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "change-me"
    minio_secure: bool = False
    raw_files_bucket: str = Field(default="raw-files", validation_alias="MINIO_BUCKET_RAW_FILES")
    parsed_results_bucket: str = Field(
        default="parsed-results",
        validation_alias="MINIO_BUCKET_PARSED_RESULTS",
    )
    normalized_docs_bucket: str = Field(
        default="normalized-docs",
        validation_alias="MINIO_BUCKET_NORMALIZED_DOCS",
    )
    message_attachments_bucket: str = "message-attachments"
    max_message_attachment_size_mb: int = 8
    mineru_api_base_url: str = "https://mineru.net"
    mineru_api_token: str = ""
    mineru_model_version: str = "vlm"
    mineru_language: str = "ch"
    mineru_enable_formula: bool = True
    mineru_enable_table: bool = True
    mineru_is_ocr: bool = True
    mineru_request_timeout_seconds: int = 30
    embedding_api_base_url: str = ""
    embedding_api_key: str = ""
    embedding_service_url: str = "http://embedding-service:8200"
    embedding_model: str = "bge-m3"
    embedding_batch_size: int = 16
    qwen_embedding_model: str = "qwen-vl-embedding"
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com"
    reranker_api_base_url: str = ""
    reranker_api_key: str = ""
    reranker_service_url: str = "http://reranker-service:8300"
    reranker_model: str = "bge-reranker"
    llm_api_base_url: str = ""
    llm_api_key: str = ""
    llm_api_base: str = ""
    llm_model: str = ""
    intent_recognition_api_base_url: str = ""
    intent_recognition_api_key: str = ""
    intent_recognition_model: str = ""
    intent_recognition_timeout_seconds: int = 30
    intent_recognition_temperature: float = 0.0
    intent_recognition_max_tokens: int = 800
    knowledge_search_classifier_api_base_url: str = ""
    knowledge_search_classifier_api_key: str = ""
    knowledge_search_classifier_model: str = "qwen3.6-flash"
    knowledge_search_classifier_timeout_seconds: int = 30
    knowledge_search_classifier_temperature: float = 0.0
    knowledge_search_classifier_max_tokens: int = 32
    assistant_profile_config_path: str = "app/config/assistant_profile.json"
    image_description_enabled: bool = True
    image_description_api_base_url: str = ""
    image_description_api_key: str = ""
    image_description_model: str = "qwen3.6-flash"
    image_description_timeout_seconds: int = 120
    image_description_temperature: float = 0.2
    image_description_max_tokens: int = 800
    evidence_min_reranker_score: float | None = None
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "chunks"
    bm25_enabled: bool = False
    bm25_provider: str = "opensearch"
    bm25_base_url: str = "http://opensearch:9200"
    bm25_index_name: str = "chunks_bm25"
    bm25_top_k: int = 50
    bm25_index_analyzer: str = "ik_max_word"
    bm25_search_analyzer: str = "ik_smart"
    demo_fixture_enabled: bool = False
    parse_worker_enabled: bool = True
    parse_worker_poll_interval_seconds: float = 5.0
    parse_worker_batch_size: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("evidence_min_reranker_score", mode="before")
    @classmethod
    def parse_optional_float(cls, value: object) -> object:
        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
