from pydantic import BaseModel, Field,BeforeValidator
from typing import Annotated, Optional

PyObjectId = Annotated[str, BeforeValidator(str)]
class Chunk(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    content:str=Field(...,min_length=1)
    metadata: dict
    chunk_order:int =Field(...,gt=0)
    project_id: str=Field(...,min_length=1)
    def __str__(self):
        return f"Chunk(_id={self._id}, project_id={self.project_id}, content={self.content}, metadata={self.metadata}, chunk_order={self.chunk_order})"