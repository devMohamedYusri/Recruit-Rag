from pydantic import BaseModel
from typing import Optional
class ProcessRequest(BaseModel):
    file_ids: Optional[list[str]] = None
    file_id: Optional[str] = None
    chunk_size: Optional[int] = 600
    chunk_overlap:Optional[int]=200
    do_reset:Optional[bool]=False
