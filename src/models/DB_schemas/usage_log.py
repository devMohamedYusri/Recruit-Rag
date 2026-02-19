from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from .types import PyObjectId

class UsageLog(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    project_id: str = Field(..., min_length=1)
    timestamp: datetime = Field(default_factory=datetime.now)
    model_id: str = Field(..., min_length=1)
    action_type: str = Field(..., description="e.g. 'screening', 'extraction', 'embedding', 'vector_search'")
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    
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
            }
        ]
