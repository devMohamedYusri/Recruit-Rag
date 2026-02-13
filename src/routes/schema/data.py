from pydantic import BaseModel
from typing import Optional
class ProcessRequest(BaseModel):
    file_ids: Optional[list[str]] = None
    file_id: Optional[str] = None
    chunk_size: Optional[int] = 100
    chunk_overlap:Optional[int]=20
    do_reset:Optional[bool]=False
