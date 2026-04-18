from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Application Settings ─────────────────────────────────────────────
    APP_NAME: str = Field(default="Recruit-Rag")
    APP_VERSION: str = Field(default="0.4")
    CORS_ORIGINS: list[str] = Field(default=["*"])

    # ── File Upload Settings ─────────────────────────────────────────────
    FILE_MAX_SIZE_MB: int = Field(default=10)
    FILE_ALLOWED_TYPES: list[str] = Field(
        default=[
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain",
            "application/pdf",
        ]
    )
    UPLOAD_DIRECTORY: str = Field(default="assets/files")
    FILE_CHUNK_SIZE: int = Field(default=512000)
    FILE_DEFAULT_CHUNK_SIZE: int = Field(default=1048576)
    FILE_BYTES_TO_MB: int = Field(default=1048576)
    UPLOAD_MAX_FILES: int = Field(default=1000)
    UPLOAD_MAX_TOTAL_SIZE_MB: int = Field(default=500)

    # ── Database Settings (MongoDB) ──────────────────────────────────────
    MONGO_DB: str = Field(default="mongodb://localhost:27017")
    DB_NAME: str = Field(default="recruit-rag")

    PROJECTS_COLLECTION: str = Field(default="PROJECTS_COLLECTION")
    CHUNKS_COLLECTION: str = Field(default="CHUNKS_COLLECTION")
    ASSETS_COLLECTION: str = Field(default="ASSETS_COLLECTION")
    RESUMES_COLLECTION: str = Field(default="RESUMES_COLLECTION")
    JOB_DESCRIPTIONS_COLLECTION: str = Field(default="JOB_DESCRIPTIONS_COLLECTION")
    USAGE_LOGS_COLLECTION: str = Field(default="USAGE_LOGS_COLLECTION")
    SCREENING_RESULTS_COLLECTION: str = Field(default="SCREENING_RESULTS_COLLECTION")
    USERS_COLLECTION: str = Field(default="USERS_COLLECTION")

    # ── LLM Configuration ────────────────────────────────────────────────
    GENERATION_BACKEND: str = Field(default="gemini")
    EMBEDDING_BACKEND: str = Field(default="gemini")

    GENERATION_MODEL_ID: str = Field(default="gemini-3-flash-preview")
    CV_EXTRACTION_MODEL_ID: str = Field(default="gemini-3-flash-preview")
    SCREENING_MODEL_ID: str = Field(default="gemini-3-pro-preview")
    EMBEDDING_MODEL_ID: str = Field(default="gemini-embedding-004")
    EMBEDDING_MODEL_SIZE: int = Field(default=768)

    # ── LLM Concurrency ──────────────────────────────────────────────────
    LLM_CONCURRENCY_LIMIT: int = Field(default=25)

    # ── API Keys ─────────────────────────────────────────────────────────
    GROQ_API_KEY: str = Field(default="")
    GEMINI_API_KEY: str = Field(default="")
    JWT_SECRET_KEY: str = Field(default="CHANGE-ME-IN-PRODUCTION-USE-ENV-VARIABLE")

    # ── Vector DB Configuration ────────────────────────────────────────
    VECTOR_DB_TYPE: str = Field(default="QDRANT")
    DB_DIRECTORY: str = Field(default="assets/database")
    VECTOR_DB_NAME: str = Field(default="vector_db")
    VECTOR_DB_DISTANCE: str = Field(default="cosine")
    VECTOR_DB_COLLECTION_NAME: str = Field(default="recruit_rag_vectors")
    QDRANT_URL: str = Field(default="")
    QDRANT_API_KEY: str = Field(default="")

    # ── S3 / Cloudflare R2 Storage ───────────────────────────────────────
    S3_ENDPOINT_URL: str = Field(default="")
    S3_ACCESS_KEY_ID: str = Field(default="")
    S3_SECRET_ACCESS_KEY: str = Field(default="")
    S3_BUCKET_NAME: str = Field(default="")

    # ── Fallback Configuration ──────────────────────────────────────────
    ENABLE_LLM_FALLBACK: bool = Field(default=True)
    DEFAULT_GROQ_MODEL: str = Field(default="llama-3.3-70b-versatile")
    SECONDARY_GROQ_MODEL: str = Field(default="llama-3.1-8b-instant")

    # ── Production Safety ────────────────────────────────────────────────
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = Field(default=60)
    MAX_TOKENS_PER_PROJECT_PER_MONTH: int = Field(default=6000000)
    LLM_TIMEOUT_SECONDS: int = Field(default=60)


@lru_cache()
def get_settings():
    return Settings()
