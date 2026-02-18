from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Annotated, Optional
from .types import PyObjectId

class Project(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    project_id: str=Field(min_length=1)
    model_config: ConfigDict = ConfigDict(
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
                "name":"project_id_index",
                "fields":[("project_id",1)],
                "unique":True
            }
        ]