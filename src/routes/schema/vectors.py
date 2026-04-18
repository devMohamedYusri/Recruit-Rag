from pydantic import BaseModel, field_validator

class SearchVectorsRequest(BaseModel):
    query_text: str
    k: int = 5
    project_id: str | None = None

    @field_validator('project_id')
    @classmethod
    def validate_project_id(cls, v):
        if v and not v.isalnum():
            raise ValueError("Project ID must be alphanumeric")
        return v
