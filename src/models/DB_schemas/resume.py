from pydantic import BaseModel, Field, BeforeValidator, ConfigDict
from typing import Annotated, Optional
from datetime import datetime

PyObjectId = Annotated[str, BeforeValidator(str)]


class Resume(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    project_id: str = Field(..., min_length=1)
    file_id: str = Field(..., min_length=1)
    candidate_name: str = Field(default="Unknown")
    contact_info: dict = Field(default_factory=dict)
    full_content: str = Field(default="")
    parsed_data: dict = Field(default_factory=dict)
    extraction_method: str = Field(default="local")  # "local" | "gemini_fallback"
    created_at: Optional[str] = Field(
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
                "name": "resume_project_id_index",
                "fields": [("project_id", 1)],
                "unique": False
            },
            {
                "name": "resume_project_file_id_index",
                "fields": [("project_id", 1), ("file_id", 1)],
                "unique": True
            }
        ]
