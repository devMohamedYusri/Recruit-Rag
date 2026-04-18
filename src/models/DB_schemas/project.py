from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional
from .types import PyObjectId
from datetime import datetime, timezone

class Project(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    project_id: str = Field(min_length=1)
    user_id: PyObjectId = Field(...)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True
    )

    @field_validator('project_id')    
    @classmethod
    def validate_project_id(cls, v):
        if not v.isalnum():
            raise ValueError("Project ID must be alphanumeric")
        return v
    
    @classmethod
    def get_indexes(cls):
        return [
            {
                "name":"project_user_unique_index",
                "fields":[("project_id", 1), ("user_id", 1)],
                "unique":True
            },
            {
                "name":"user_id_index",
                "fields":[("user_id",1)],
                "unique":False
            }
        ]