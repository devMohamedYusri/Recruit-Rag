from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional
from datetime import datetime, timezone
from .types import PyObjectId

class JobDescription(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    project_id: str = Field(..., min_length=1)
    user_id: PyObjectId = Field(...)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    prompt: Optional[str] = Field(default=None)
    weights: Optional[dict[str, float]] = Field(default_factory=dict)
    custom_rubric: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
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
                "name": "jd_project_id_index",
                "fields": [("project_id", 1)],
                "unique": True
            },
            {
                "name": "jd_user_id_index",
                "fields": [("user_id", 1)],
                "unique": False
            }
        ]
