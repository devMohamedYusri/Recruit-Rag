from pydantic import BaseModel

class SearchVectorsRequest(BaseModel):
    query_text: str
    k: int = 5
    project_id: str | None = None
