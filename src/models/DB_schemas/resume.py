from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional
from datetime import datetime, timezone
from .types import PyObjectId


class Resume(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    project_id: str = Field(..., min_length=1)
    user_id: PyObjectId = Field(...)
    file_id: str = Field(..., min_length=1)
    candidate_name: str = Field(default="Unknown")
    contact_info: dict = Field(default_factory=dict)
    full_content: str = Field(default="")
    parsed_data: dict = Field(default_factory=dict)
    extraction_method: str = Field(default="local")  # "local" | "gemini_fallback"
    temp_extraction_time: Optional[float] = Field(default=0.0, exclude=True)
    
    # Hard Determinism Tracking
    resume_hash: Optional[str] = Field(default=None, description="SHA256 of normalized CV text")
    embedding_version: Optional[str] = Field(default=None)
    screening_version: Optional[str] = Field(default=None)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config: ConfigDict = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True
    )

    @field_validator('project_id')
    @classmethod
    def validate_project_id(cls, v):
        if v and not v.isalnum():
            raise ValueError("Project ID must be alphanumeric")
        return v

    @classmethod
    def get_indexes(cls):
        return [
            {
                "name": "resume_project_id_index",
                "fields": [("project_id", 1)],
                "unique": False
            },
            {
                "name": "resume_user_id_index",
                "fields": [("user_id", 1)],
                "unique": False
            },
            {
                "name": "resume_project_file_id_index",
                "fields": [("project_id", 1), ("file_id", 1)],
                "unique": True
            }
        ]
