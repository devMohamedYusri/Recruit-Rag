from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from .types import PyObjectId

class JobDescription(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    project_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    prompt: Optional[str] = Field(default=None)
    weights: Optional[dict[str, float]] = Field(default_factory=dict)
    custom_rubric: Optional[str] = Field(default=None)
    created_at: Optional[str] = Field(
        default_factory=lambda: datetime.now().isoformat()
    )
    updated_at: Optional[str] = Field(
        default_factory=lambda: datetime.now().isoformat()
    )
    model_config: ConfigDict = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True
    )

    @classmethod
    def get_indexes(cls):
        return [
            {
                "name": "jd_project_id_index",
                "fields": [("project_id", 1)],
                "unique": True
            }
        ]
