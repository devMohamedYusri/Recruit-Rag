from pydantic import Field
from pydantic_settings import BaseSettings,SettingsConfigDict
from functools import lru_cache



class settings(BaseSettings):
    model_config=SettingsConfigDict(env_file=".env",env_file_encoding="utf-8")
    APP_NAME:str =Field(default="Recruit Rag")
    APP_VERSION:str=Field(default='1.0.0')
    
    FILE_MAX_SIZE_MB:int=Field(default=3)
    FILE_ALLOWED_TYPES:list[str]=Field(default=["text/plain","application/pdf"])
    UPLOAD_DIRECTORY:str=Field(default="/assets/files")
    FILE_CHUNK_SIZE:int=Field(default=512000)
    FILE_DEFAULT_CHUNK_SIZE:int=Field(default=1048576)
    FILE_BYTES_TO_MB:int=Field(default=1024*1024)

    MONGO_DB:str=Field(default="mongodb://localhost:27017")
    DB_NAME:str=Field(default="recruit-rag")

    PROJECTS_COLLECTION:str=Field(default="PROJECTS_COLLECTION")
    CHUNKS_COLLECTION:str=Field(default="CHUNKS_COLLECTION")
    ASSETS_COLLECTION:str=Field(default="ASSETS_COLLECTION")

@lru_cache()   
def get_settings():
    return settings()