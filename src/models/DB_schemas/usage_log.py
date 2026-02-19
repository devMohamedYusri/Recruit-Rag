from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from .types import PyObjectId

class UsageLog(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    project_id: str = Field(..., min_length=1)
    file_id: Optional[str] = Field(default=None, description="Resume file_id this log entry relates to")
    timestamp: datetime = Field(default_factory=datetime.now)
    model_id: str = Field(..., min_length=1)
    action_type: str = Field(..., description="e.g. 'screening', 'cv_extraction_fallback', 'cv_structuring_batch', 'jd_extraction'")
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    latency_ms: int = Field(default=0, description="LLM call duration in milliseconds")
    model_config: ConfigDict = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True
    )

    @classmethod
    def get_indexes(cls):
        return [
            {
                "name": "usage_project_index",
                "fields": [("project_id", 1)],
                "unique": False
            },
            {
                "name": "usage_timestamp_index",
                "fields": [("timestamp", -1)],
                "unique": False
            },
            {
                "name": "usage_file_id_index",
                "fields": [("project_id", 1), ("file_id", 1)],
                "unique": False
            }
        ]
