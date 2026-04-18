from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional
from datetime import datetime, timezone
from .types import PyObjectId

class ScreeningResultDB(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    project_id: str = Field(..., min_length=1)
    user_id: PyObjectId = Field(...)
    file_id: str = Field(..., min_length=1)
    
    # Hard Determinism Tracking
    resume_hash: Optional[str] = Field(default=None)
    job_hash: Optional[str] = Field(default=None)
    scoring_version: Optional[str] = Field(default=None)
    feature_version: Optional[str] = Field(default=None)
    
    # Two-Phase Routing Scores
    base_score: Optional[float] = Field(default=None)
    adjustment: Optional[int] = Field(default=None)
    final_score: Optional[float] = Field(default=None)
    
    result: dict = Field(..., description="The structured ScreeningResult dictionary")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
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
                "name": "screening_project_index",
                "fields": [("project_id", 1)],
                "unique": False
            },
            {
                "name": "screening_user_index",
                "fields": [("user_id", 1)],
                "unique": False
            },
            {
                "name": "screening_file_index",
                "fields": [("project_id", 1), ("file_id", 1)],
                "unique": False
            },
            {
                "name": "screening_timestamp_index",
                "fields": [("timestamp", -1)],
                "unique": False
            }
        ]
