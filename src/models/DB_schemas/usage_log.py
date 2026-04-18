from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime, timezone
from .types import PyObjectId


class UsageLog(BaseModel):
    id: Optional[PyObjectId] = Field(None, alias="_id")
    user_id: PyObjectId = Field(...)
    project_id: Optional[str] = None
    file_id: Optional[str] = None
    model_id: Optional[str] = None
    action_type: str = Field(...)          # e.g. "screening", "cv_extraction_fallback", "cv_structuring_batch", "jd_extraction"
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    latency_ms: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config: ConfigDict = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True
    )

    @classmethod
    def get_indexes(cls):
        return [
            {
                "name": "usage_user_id_index",
                "fields": [("user_id", 1)],
                "unique": False
            },
            {
                "name": "usage_project_index",
                "fields": [("project_id", 1)],
                "unique": False
            },
            {
                "name": "usage_created_at_index",
                "fields": [("created_at", 1)],
                "unique": False
            }
        ]
