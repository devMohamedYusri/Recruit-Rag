from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime
from .types import PyObjectId

class Asset(BaseModel):
    id: Optional[PyObjectId] = Field(None, alias="_id",description="Unique identifier for the asset")
    project_id: str = Field(None, description="Reference to the associated asset project")
    name: str = Field(..., description="Name of the asset")
    type: str = Field(..., description="Type of the asset (e.g., image, video, document)")
    size_in_bytes: Optional[int] = Field(None, description="Size of the asset in bytes")
    url: str = Field(..., description="URL where the asset is stored")
    metadata: Optional[dict] = Field(None, description="Additional metadata related to the asset")
    created_at: Optional[str] = Field(default_factory=lambda: datetime.now().isoformat(), description="Timestamp when the asset was created")
    updated_at: Optional[str] = Field(default_factory=lambda: datetime.now().isoformat(), description="Timestamp when the asset was last updated")
    model_config: ConfigDict = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True
        )
    @classmethod
    def get_indexes(cls):
        return [
            {
                "name":"asset_project_id_index",
                "fields":[("project_id",1)],
                "unique":False
            },
            {
                "name":"asset_project_name_id_index",
                "fields":[("project_id",1),("name",1)],
                "unique":True
            }
        ]