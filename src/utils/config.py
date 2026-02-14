from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ── Application Settings ─────────────────────────────────────────────
    APP_NAME: str = Field(default="Recruit-Rag")
    APP_VERSION: str = Field(default="0.4")

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

    # ── Database Settings (MongoDB) ──────────────────────────────────────
    MONGO_DB: str = Field(default="mongodb://localhost:27017")
    DB_NAME: str = Field(default="recruit-rag")

    PROJECTS_COLLECTION: str = Field(default="PROJECTS_COLLECTION")
    CHUNKS_COLLECTION: str = Field(default="CHUNKS_COLLECTION")
    ASSETS_COLLECTION: str = Field(default="ASSETS_COLLECTION")

    # ── LLM Configuration ────────────────────────────────────────────────
    GENERATION_BACKEND: str = Field(default="gemini")
    EMBEDDING_BACKEND: str = Field(default="groq")

    GENERATION_MODEL_ID: str = Field(default="llama-3.3-70b-versatile")
    EMBEDDING_MODEL_ID: str = Field(default="gemini-embedding-001")
    EMBEDDING_MODEL_SIZE: int = Field(default=768)

    # ── API Keys ─────────────────────────────────────────────────────────
    GROQ_API_KEY: str = Field(default="")
    GEMINI_API_KEY: str = Field(default="")

    # ── Vector DB Configuration ────────────────────────────────────────
    VECTOR_DB_TYPE: str = Field(default="QDRANT")
    DB_DIRECTORY: str = Field(default="assets/database")
    VECTOR_DB_NAME: str = Field(default="vector_db")
    VECTOR_DB_DISTANCE: str = Field(default="cosine")
    VECTOR_DB_COLLECTION_NAME: str = Field(default="chunks")



@lru_cache()
def get_settings():
    return Settings()