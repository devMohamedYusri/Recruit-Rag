from typing import Optional, List
from pydantic import BaseModel

class UpsertVectorsRequest(BaseModel):
    do_reset: Optional[bool] = False

class SearchVectorsRequest(BaseModel):
    query_text: str
    k: int = 5