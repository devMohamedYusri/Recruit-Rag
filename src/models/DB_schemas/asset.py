from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional
from datetime import datetime, timezone
from .types import PyObjectId

class Asset(BaseModel):
    id: Optional[PyObjectId] = Field(None, alias="_id",description="Unique identifier for the asset")
    project_id: str = Field(None, description="Reference to the associated asset project")
    user_id: PyObjectId = Field(...)
    name: str = Field(..., description="Name of the asset")
    type: str = Field(..., description="Type of the asset (e.g., image, video, document)")
    size_in_bytes: Optional[int] = Field(None, description="Size of the asset in bytes")
    url: str = Field(..., description="URL where the asset is stored")
    metadata: Optional[dict] = Field(None, description="Additional metadata related to the asset")
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
                "name":"asset_project_id_index",
                "fields":[("project_id",1)],
                "unique":False
            },
            {
                "name":"asset_user_id_index",
                "fields":[("user_id",1)],
                "unique":False
            },
            {
                "name":"asset_project_name_id_index",
                "fields":[("project_id",1),("name",1)],
                "unique":True
            }
        ]